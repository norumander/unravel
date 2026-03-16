import { useCallback, useEffect, useState } from 'react'
import type { DiagnosticReport, SSEEvent } from '../types/api'
import { useSSE } from '../hooks/useSSE'
import { downloadMarkdown } from '../utils/exportMarkdown'

interface ReportPhaseProps {
  sessionId: string
  onReportComplete: (report: DiagnosticReport) => void
}

const SEVERITY_ORDER = { critical: 0, warning: 1, info: 2 } as const
const SEVERITY_COLORS = {
  critical: 'bg-red-100 text-red-800 border-red-200',
  warning: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  info: 'bg-blue-100 text-blue-800 border-blue-200',
} as const

type SeverityFilter = 'all' | 'critical+warning' | 'critical'

export function ReportPhase({ sessionId, onReportComplete }: ReportPhaseProps) {
  const [streamedText, setStreamedText] = useState('')
  const [report, setReport] = useState<DiagnosticReport | null>(null)
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('all')

  const handleEvent = useCallback(
    (event: SSEEvent) => {
      if (event.type === 'report') {
        setReport(event.report)
        onReportComplete(event.report)
      }
    },
    [onReportComplete],
  )

  const handleChunk = useCallback((content: string) => {
    setStreamedText((prev) => prev + content)
  }, [])

  const { isStreaming, error, startStream } = useSSE({
    onChunk: handleChunk,
    onEvent: handleEvent,
  })

  useEffect(() => {
    startStream(`/api/analyze/${sessionId}`)
  }, [sessionId, startStream])

  const filteredFindings = report
    ? report.findings.filter((f) => {
        if (severityFilter === 'all') return true
        if (severityFilter === 'critical+warning') return f.severity !== 'info'
        return f.severity === 'critical'
      })
    : []

  const sortedFindings = [...filteredFindings].sort(
    (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity],
  )

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold text-gray-900">Diagnostic Report</h2>
          {isStreaming && (
            <span
              data-testid="streaming-indicator"
              className="inline-block h-2 w-2 animate-pulse rounded-full bg-green-500"
            />
          )}
        </div>
        {report && (
          <button
            data-testid="download-report"
            onClick={() => downloadMarkdown(report)}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
          >
            Download Report
          </button>
        )}
      </div>

      {error && (
        <div
          data-testid="report-error"
          className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          {error}
        </div>
      )}

      {!report && isStreaming && (
        <div data-testid="streaming-content" className="rounded-md bg-gray-50 p-4">
          <pre className="whitespace-pre-wrap text-sm text-gray-600">{streamedText}</pre>
        </div>
      )}

      {report && (
        <div data-testid="report-content" className="space-y-6">
          <div className="rounded-md bg-gray-50 p-4">
            <h3 className="mb-2 text-sm font-medium text-gray-500">Executive Summary</h3>
            <p className="text-gray-800">{report.executive_summary}</p>
          </div>

          {report.truncation_notes && (
            <div className="rounded-md bg-amber-50 px-4 py-2 text-sm text-amber-700">
              Note: {report.truncation_notes}
            </div>
          )}

          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-gray-500">
                Findings ({sortedFindings.length}
                {severityFilter !== 'all' ? ` of ${report.findings.length}` : ''})
              </h3>
              <div data-testid="severity-filter" className="flex gap-1">
                {([
                  ['all', 'All'],
                  ['critical+warning', 'Critical + Warning'],
                  ['critical', 'Critical Only'],
                ] as const).map(([value, label]) => (
                  <button
                    key={value}
                    onClick={() => setSeverityFilter(value)}
                    className={`rounded px-2 py-1 text-xs font-medium transition-colors ${
                      severityFilter === value
                        ? 'bg-gray-800 text-white'
                        : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            {sortedFindings.map((finding, idx) => (
              <div
                key={idx}
                className={`rounded-md border p-4 ${SEVERITY_COLORS[finding.severity]}`}
              >
                <div className="mb-2 flex items-center gap-2">
                  <span className="rounded px-2 py-0.5 text-xs font-semibold uppercase">
                    {finding.severity}
                  </span>
                  <h4 className="font-medium">{finding.title}</h4>
                </div>
                <p className="mb-2 text-sm">{finding.description}</p>
                <div className="space-y-1 text-sm">
                  <p>
                    <span className="font-medium">Root Cause:</span> {finding.root_cause}
                  </p>
                  <p>
                    <span className="font-medium">Remediation:</span> {finding.remediation}
                  </p>
                  {finding.sources && finding.sources.length > 0 && (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-xs font-medium opacity-70">
                        Sources ({finding.sources.length})
                      </summary>
                      <div className="mt-1 space-y-1">
                        {finding.sources.map((src, si) => (
                          <div
                            key={si}
                            className="rounded border border-current/10 bg-white/50 px-2 py-1 text-xs"
                          >
                            <span className="font-mono opacity-70">{src.file_path}</span>
                            <pre className="mt-0.5 whitespace-pre-wrap opacity-80">{src.excerpt}</pre>
                          </div>
                        ))}
                      </div>
                    </details>
                  )}
                  <p className="text-xs opacity-70">
                    Signals: {finding.source_signals.join(', ')}
                  </p>
                </div>
              </div>
            ))}
          </div>

          <div className="text-xs text-gray-400">
            Signal types analyzed: {report.signal_types_analyzed.join(', ')}
          </div>
        </div>
      )}
    </div>
  )
}
