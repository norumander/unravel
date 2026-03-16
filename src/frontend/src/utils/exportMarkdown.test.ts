import { describe, it, expect } from 'vitest'
import { reportToMarkdown } from './exportMarkdown'
import type { DiagnosticReport } from '../types/api'

describe('reportToMarkdown', () => {
  const baseReport: DiagnosticReport = {
    executive_summary: 'Cluster has OOM issues.',
    findings: [
      {
        severity: 'critical',
        title: 'OOMKilled Pod',
        description: 'Pod nginx is being OOM killed',
        root_cause: 'Memory limit too low',
        remediation: 'Increase memory limit',
        source_signals: ['pod_logs', 'events'],
        sources: [
          { file_path: 'logs/pod.log', excerpt: 'OOMKilled' },
        ],
      },
      {
        severity: 'info',
        title: 'Healthy node',
        description: 'Node is healthy',
        root_cause: 'N/A',
        remediation: 'None',
        source_signals: ['node_status'],
      },
    ],
    signal_types_analyzed: ['pod_logs', 'events', 'node_status'],
    truncation_notes: null,
  }

  it('includes executive summary', () => {
    const md = reportToMarkdown(baseReport)
    expect(md).toContain('Cluster has OOM issues.')
  })

  it('includes findings sorted by severity', () => {
    const md = reportToMarkdown(baseReport)
    const criticalIdx = md.indexOf('CRITICAL')
    const infoIdx = md.indexOf('INFO')
    expect(criticalIdx).toBeLessThan(infoIdx)
  })

  it('includes source citations when present', () => {
    const md = reportToMarkdown(baseReport)
    expect(md).toContain('logs/pod.log')
    expect(md).toContain('OOMKilled')
  })

  it('includes truncation notes when present', () => {
    const report = { ...baseReport, truncation_notes: 'node_status truncated by 50%' }
    const md = reportToMarkdown(report)
    expect(md).toContain('node_status truncated by 50%')
  })
})
