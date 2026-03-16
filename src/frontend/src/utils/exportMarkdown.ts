import type { DiagnosticReport } from '../types/api'

export function reportToMarkdown(report: DiagnosticReport): string {
  const lines: string[] = []

  lines.push('# Diagnostic Report')
  lines.push('')
  lines.push('## Executive Summary')
  lines.push('')
  lines.push(report.executive_summary)
  lines.push('')

  if (report.truncation_notes) {
    lines.push(`> **Note:** ${report.truncation_notes}`)
    lines.push('')
  }

  lines.push(`## Findings (${report.findings.length})`)
  lines.push('')

  const severityOrder = { critical: 0, warning: 1, info: 2 } as const
  const sorted = [...report.findings].sort(
    (a, b) => severityOrder[a.severity] - severityOrder[b.severity],
  )

  for (const finding of sorted) {
    const icon = finding.severity === 'critical' ? '🔴' : finding.severity === 'warning' ? '🟡' : '🔵'
    lines.push(`### ${icon} [${finding.severity.toUpperCase()}] ${finding.title}`)
    lines.push('')
    lines.push(finding.description)
    lines.push('')
    lines.push(`**Root Cause:** ${finding.root_cause}`)
    lines.push('')
    lines.push(`**Remediation:** ${finding.remediation}`)
    lines.push('')
    if (finding.sources && finding.sources.length > 0) {
      lines.push('**Sources:**')
      for (const src of finding.sources) {
        lines.push(`- \`${src.file_path}\`: ${src.excerpt}`)
      }
      lines.push('')
    }

    lines.push(`*Signals: ${finding.source_signals.join(', ')}*`)
    lines.push('')
    lines.push('---')
    lines.push('')
  }

  lines.push(`*Signal types analyzed: ${report.signal_types_analyzed.join(', ')}*`)

  return lines.join('\n')
}

export function downloadMarkdown(report: DiagnosticReport): void {
  const markdown = reportToMarkdown(report)
  const blob = new Blob([markdown], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'diagnostic-report.md'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
