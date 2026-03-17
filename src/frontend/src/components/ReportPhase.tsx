import { useCallback, useEffect, useRef, useState } from 'react'
import type { BundleManifest, DiagnosticReport, SSEEvent } from '../types/api'
import { useSSE } from '../hooks/useSSE'
import { downloadMarkdown } from '../utils/exportMarkdown'
import { Timeline } from './Timeline'

interface ReportPhaseProps {
  sessionId: string
  manifest: BundleManifest
  signalSummary: Record<string, number>
  onReportComplete: (report: DiagnosticReport) => void
  onFileSelect?: (path: string, excerpt?: string) => void
  onToast?: (type: 'warning' | 'error', message: string) => void
}

const SEVERITY_ORDER = { critical: 0, warning: 1, info: 2 } as const

type SeverityFilter = 'all' | 'critical+warning' | 'critical'

type StepStatus = 'done' | 'active' | 'pending'

interface Step {
  label: string
  detail: string
  status: StepStatus
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatSignalSummary(summary: Record<string, number>): string {
  return Object.entries(summary)
    .map(([key, count]) => `${key}: ${count}`)
    .join(', ')
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5 text-emerald-400">
      <path
        fillRule="evenodd"
        d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.06l2.5 2.5a.75.75 0 001.137-.089l4-5.5z"
        clipRule="evenodd"
      />
    </svg>
  )
}

function ActiveDot() {
  return (
    <span className="flex h-5 w-5 items-center justify-center">
      <span className="absolute h-3 w-3 animate-ping rounded-full bg-teal-400 opacity-40" />
      <span className="relative h-2.5 w-2.5 rounded-full bg-teal-500" />
    </span>
  )
}

function PendingCircle() {
  return (
    <span className="flex h-5 w-5 items-center justify-center">
      <span className="h-3 w-3 rounded-full border-2 border-zinc-700" />
    </span>
  )
}

function StepIcon({ status }: { status: StepStatus }) {
  if (status === 'done') return <CheckIcon />
  if (status === 'active') return <ActiveDot />
  return <PendingCircle />
}

function ProgressStepper({ steps }: { steps: Step[] }) {
  return (
    <div
      data-testid="progress-stepper"
      className="rounded-xl border border-zinc-800 bg-zinc-900 p-6"
    >
      <div className="space-y-0">
        {steps.map((step, idx) => (
          <div key={step.label} className="flex gap-3">
            {/* Icon column with connecting line */}
            <div className="flex flex-col items-center">
              <div className="relative flex-shrink-0">
                <StepIcon status={step.status} />
              </div>
              {idx < steps.length - 1 && (
                <div className={`h-6 border-l-2 transition-colors duration-500 ${
                  step.status === 'done' ? 'border-teal-600' : 'border-zinc-800'
                }`} />
              )}
            </div>
            {/* Text column */}
            <div className="pb-6">
              <span
                className={`text-sm font-medium ${
                  step.status === 'active'
                    ? 'text-zinc-200'
                    : step.status === 'done'
                      ? 'text-zinc-300'
                      : 'text-zinc-500'
                }`}
              >
                {step.label}
              </span>
              {step.detail && (
                <span className="ml-2 text-sm text-zinc-500">&mdash; {step.detail}</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch { /* clipboard may be unavailable */ }
  }
  return (
    <button
      onClick={handleCopy}
      className="ml-1 inline-flex items-center rounded px-1 py-0.5 text-xs text-zinc-500 hover:bg-zinc-700 hover:text-zinc-300"
      title="Copy to clipboard"
    >
      {copied ? (
        <span className="text-emerald-400">Copied!</span>
      ) : (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-3 w-3">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
      )}
    </button>
  )
}

export function ReportPhase({
  sessionId,
  manifest,
  signalSummary,
  onReportComplete,
  onFileSelect,
  onToast,
}: ReportPhaseProps) {
  const [report, setReport] = useState<DiagnosticReport | null>(null)
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('all')
  const [analysisComplete, setAnalysisComplete] = useState(false)
  const startedRef = useRef(false)

  const handleEvent = useCallback(
    (event: SSEEvent) => {
      if (event.type === 'report') {
        setReport(event.report)
        onReportComplete(event.report)
      }
    },
    [onReportComplete],
  )

  const handleChunk = useCallback(() => {
    // Chunks are consumed silently — the stepper replaces raw text display
  }, [])

  const { isStreaming, error, startStream, stopStream } = useSSE({
    onChunk: handleChunk,
    onEvent: handleEvent,
    onWarning: useCallback((msg: string) => onToast?.('warning', msg), [onToast]),
    onError: useCallback((msg: string) => onToast?.('error', msg), [onToast]),
  })

  useEffect(() => {
    if (!isStreaming && startedRef.current && !report) {
      setAnalysisComplete(true)
    }
  }, [isStreaming, report])

  useEffect(() => {
    // Guard against StrictMode double-mount
    if (startedRef.current) return
    startedRef.current = true
    startStream(`/api/analyze/${sessionId}`)
    return () => {
      stopStream()
    }
  }, [sessionId, startStream, stopStream])

  // Build stepper steps
  const steps: Step[] = [
    {
      label: 'Bundle extracted',
      detail: `${manifest.total_files} files, ${formatBytes(manifest.total_size_bytes)}`,
      status: 'done',
    },
    {
      label: 'Signals classified',
      detail: formatSignalSummary(signalSummary),
      status: 'done',
    },
    {
      label: report || analysisComplete ? 'Analysis complete' : 'Analyzing with AI...',
      detail: '',
      status: report || analysisComplete ? 'done' : isStreaming ? 'active' : 'pending',
    },
    {
      label: 'Building report',
      detail: '',
      status: report ? 'done' : 'pending',
    },
  ]

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

  const severityBorderColor = {
    critical: 'border-l-[3px] border-red-500 bg-red-500/[0.04] shadow-[inset_0_0_20px_rgba(239,68,68,0.04)]',
    warning: 'border-l-[3px] border-amber-500 bg-amber-500/[0.03] shadow-[inset_0_0_20px_rgba(245,158,11,0.03)]',
    info: 'border-l-[3px] border-zinc-600 bg-zinc-500/[0.06]',
  } as const

  const severityBadgeColor = {
    critical: 'bg-red-500/10 text-red-400',
    warning: 'bg-amber-500/10 text-amber-400',
    info: 'bg-zinc-500/10 text-zinc-400',
  } as const

  const severityDotColor = {
    critical: 'bg-red-500',
    warning: 'bg-amber-500',
    info: 'bg-zinc-500',
  } as const

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold text-zinc-100">Diagnostic Report</h2>
          {isStreaming && (
            <span
              data-testid="streaming-indicator"
              role="status"
              aria-label="Analysis in progress"
              className="inline-block h-2 w-2 animate-pulse rounded-full bg-emerald-500"
            />
          )}
        </div>
        {report && (
          <button
            data-testid="download-report"
            onClick={() => downloadMarkdown(report)}
            className="rounded-lg border border-zinc-700 px-3 py-1.5 text-sm text-zinc-400 transition-all duration-200 hover:bg-zinc-800 hover:text-zinc-200 hover:shadow-lg hover:shadow-teal-500/10"
          >
            Download Report
          </button>
        )}
      </div>

      {/* Error */}
      {error && (
        <div
          data-testid="report-error"
          className="rounded-lg border border-red-900/50 bg-red-950/40 px-4 py-3 text-sm text-red-400"
        >
          {error}
        </div>
      )}

      {/* Progress Stepper — shown during analysis */}
      {!report && (
        <div data-testid="streaming-content">
          <ProgressStepper steps={steps} />
        </div>
      )}

      {/* Report Content */}
      {report && (
        <div data-testid="report-content" className="space-y-6">
          {/* Executive Summary */}
          <div className="animate-fade-in-up rounded-xl border border-zinc-800 bg-zinc-900 p-5">
            <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-500">
              Executive Summary
            </h3>
            <p className="leading-relaxed text-zinc-200">{report.executive_summary}</p>
          </div>

          {/* Event Timeline */}
          {report.timeline && report.timeline.length > 0 && (
            <div className="animate-fade-in-up" style={{ animationDelay: '100ms' }}>
              <Timeline events={report.timeline} />
            </div>
          )}

          {/* Truncation Note */}
          {report.truncation_notes && (
            <div className="rounded-lg border border-amber-900/30 bg-amber-950/30 px-4 py-2 text-sm text-amber-400">
              Note: {report.truncation_notes}
            </div>
          )}

          {/* Findings */}
          <div className="animate-fade-in-up space-y-4" style={{ animationDelay: '200ms' }}>
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-zinc-500">
                Findings ({sortedFindings.length}
                {severityFilter !== 'all' ? ` of ${report.findings.length}` : ''})
              </h3>
              <div
                data-testid="severity-filter"
                className="flex gap-1"
                role="group"
                aria-label="Filter by severity"
              >
                {(
                  [
                    ['all', 'All'],
                    ['critical+warning', 'Critical + Warning'],
                    ['critical', 'Critical Only'],
                  ] as const
                ).map(([value, label]) => (
                  <button
                    key={value}
                    onClick={() => setSeverityFilter(value)}
                    aria-pressed={severityFilter === value}
                    className={`rounded px-2 py-1 text-xs font-medium transition-colors ${
                      severityFilter === value
                        ? 'bg-zinc-200 text-zinc-900'
                        : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {sortedFindings.map((finding, idx) => (
              <div
                key={`${finding.severity}-${finding.title}-${idx}`}
                className={`animate-fade-in-up rounded-lg p-4 transition-all duration-200 hover:translate-x-0.5 ${severityBorderColor[finding.severity]}`}
                style={{ animationDelay: `${idx * 80}ms` }}
              >
                <div className="mb-2 flex items-center gap-2">
                  <span
                    className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide ${severityBadgeColor[finding.severity]}`}
                  >
                    <span className={`h-1.5 w-1.5 rounded-full ${severityDotColor[finding.severity]}`} />
                    {finding.severity}
                  </span>
                  <h4 className="font-medium text-zinc-100">{finding.title}</h4>
                </div>
                <p className="mb-3 text-sm text-zinc-300">{finding.description}</p>
                <div className="space-y-1.5 text-sm">
                  <p>
                    <span className="font-medium text-zinc-500">Root Cause:</span>{' '}
                    <span className="text-zinc-300">{finding.root_cause}</span>
                  </p>
                  <div className="flex items-start gap-1">
                    <p className="flex-1">
                      <span className="font-medium text-zinc-500">Remediation:</span>{' '}
                      <span className="text-zinc-300">{finding.remediation}</span>
                    </p>
                    <CopyButton text={finding.remediation} />
                  </div>
                  {finding.sources && finding.sources.length > 0 && (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-xs text-zinc-400">
                        Sources ({finding.sources.length})
                      </summary>
                      <div className="mt-1.5 space-y-1.5">
                        {finding.sources.map((src, si) => (
                          <div
                            key={si}
                            className="rounded border border-zinc-700/50 bg-zinc-800/60 px-3 py-2 text-xs text-zinc-400"
                          >
                            {onFileSelect ? (
                              <button
                                onClick={() => onFileSelect(src.file_path, src.excerpt)}
                                className="font-mono text-teal-400 hover:text-teal-300 hover:underline"
                              >
                                {src.file_path}
                              </button>
                            ) : (
                              <span className="font-mono">{src.file_path}</span>
                            )}
                            <pre className="mt-1 whitespace-pre-wrap text-zinc-400">
                              {src.excerpt}
                            </pre>
                          </div>
                        ))}
                      </div>
                    </details>
                  )}
                  <p className="text-xs text-zinc-500">
                    Signals: {finding.source_signals.join(', ')}
                  </p>
                </div>
              </div>
            ))}
          </div>

          {/* Footer */}
          <div className="text-xs text-zinc-600">
            Signal types analyzed: {report.signal_types_analyzed.join(', ')}
          </div>
        </div>
      )}
    </div>
  )
}
