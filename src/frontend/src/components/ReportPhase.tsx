import { useCallback, useEffect, useState } from 'react'
import type { DiagnosticReport, SSEEvent } from '../types/api'
import { useSSE } from '../hooks/useSSE'

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

export function ReportPhase({ sessionId, onReportComplete }: ReportPhaseProps) {
  const [streamedText, setStreamedText] = useState('')
  const [report, setReport] = useState<DiagnosticReport | null>(null)

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

  const sortedFindings = report
    ? [...report.findings].sort(
        (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity],
      )
    : []

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <h2 className="text-lg font-semibold text-gray-900">Diagnostic Report</h2>
        {isStreaming && (
          <span
            data-testid="streaming-indicator"
            className="inline-block h-2 w-2 animate-pulse rounded-full bg-green-500"
          />
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
            <h3 className="text-sm font-medium text-gray-500">
              Findings ({sortedFindings.length})
            </h3>
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
