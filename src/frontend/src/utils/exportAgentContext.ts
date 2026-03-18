import type { ChatMessage, DiagnosticReport } from '../types/api'

/**
 * Generate structured context optimized for pasting into a coding agent
 * (Claude Code, Cursor, etc.) to investigate and resolve K8s issues.
 */
export function buildAgentContext(
  report: DiagnosticReport,
  chatMessages: ChatMessage[],
): string {
  const lines: string[] = []

  const severityOrder = { critical: 0, warning: 1, info: 2 } as const
  const sorted = [...report.findings].sort(
    (a, b) => severityOrder[a.severity] - severityOrder[b.severity],
  )

  // Agent instructions
  lines.push('# Kubernetes Cluster Issue Investigation')
  lines.push('')
  lines.push('You are investigating issues in a Kubernetes cluster identified by automated support bundle analysis. Below is a structured diagnostic report with findings ranked by severity, supporting evidence from bundle files, and (if available) notes from a follow-up investigation.')
  lines.push('')
  lines.push('Work through the priority actions in order. For each action: verify the issue still exists, apply the remediation, and confirm the fix. Use the evidence file paths and excerpts to guide your investigation.')
  lines.push('')

  // Priority checklist
  const actionable = sorted.filter((f) => f.severity !== 'info')
  if (actionable.length > 0) {
    lines.push('## Priority Actions')
    lines.push('')
    for (let i = 0; i < actionable.length; i++) {
      const f = actionable[i]
      const tag = f.severity === 'critical' ? 'CRITICAL' : 'WARNING'
      lines.push(`${i + 1}. [ ] [${tag}] ${f.title} — ${f.remediation}`)
    }
    lines.push('')
  }

  // Situation
  lines.push('## Situation')
  lines.push('')
  lines.push(report.executive_summary)
  lines.push('')

  // Timeline
  if (report.timeline && report.timeline.length > 0) {
    lines.push('## Event Timeline')
    lines.push('')
    for (const event of report.timeline) {
      lines.push(`- \`${event.timestamp}\` [${event.severity}] ${event.title} — ${event.description} (source: \`${event.source}\`)`)
    }
    lines.push('')
  }

  // Findings detail
  lines.push(`## Findings (${sorted.length})`)
  lines.push('')

  for (const finding of sorted) {
    lines.push(`### [${finding.severity.toUpperCase()}] ${finding.title}`)
    lines.push('')
    lines.push(finding.description)
    lines.push('')
    lines.push(`**Root cause:** ${finding.root_cause}`)
    lines.push('')
    lines.push(`**Remediation:** ${finding.remediation}`)
    lines.push('')
    if (finding.sources && finding.sources.length > 0) {
      lines.push('**Evidence:**')
      for (const src of finding.sources) {
        lines.push(`- \`${src.file_path}\``)
        if (src.excerpt) {
          lines.push('  ```')
          lines.push(`  ${src.excerpt}`)
          lines.push('  ```')
        }
      }
      lines.push('')
    }
  }

  // Chat investigation notes
  const assistantInsights = chatMessages
    .filter((m) => m.role === 'assistant' && m.content.trim().length > 50)

  if (assistantInsights.length > 0) {
    lines.push('## Investigation Notes')
    lines.push('')
    lines.push('The following insights were gathered during a follow-up investigation of the bundle. These may contain additional context, file contents, or analysis not captured in the findings above.')
    lines.push('')
    for (const msg of assistantInsights) {
      lines.push(msg.content.trim())
      lines.push('')
      lines.push('---')
      lines.push('')
    }
  }

  return lines.join('\n')
}
