import { describe, it, expect } from 'vitest'
import { buildAgentContext } from './exportAgentContext'
import type { DiagnosticReport, ChatMessage } from '../types/api'

const baseReport: DiagnosticReport = {
  executive_summary: 'Cluster has OOM issues and disk pressure.',
  findings: [
    {
      severity: 'critical',
      title: 'OOMKilled Pod',
      description: 'Pod auth-service is being OOM killed',
      root_cause: 'Memory limit too low at 512Mi',
      remediation: 'Run `kubectl edit deployment auth-service` and increase memory to 1Gi',
      source_signals: ['pod_logs', 'events'],
      sources: [
        { file_path: 'logs/auth-service.log', excerpt: 'OOMKilled process 1842' },
      ],
    },
    {
      severity: 'warning',
      title: 'Image Pull Failure',
      description: 'api-gateway failed to pull image v2.4.1',
      root_cause: 'Image tag not found in registry',
      remediation: 'Fix the image tag in the deployment spec',
      source_signals: ['events'],
    },
    {
      severity: 'info',
      title: 'HPA Rescaled',
      description: 'HPA rescaled auth-service to 5 pods',
      root_cause: 'High CPU utilization triggered autoscaling',
      remediation: 'No action needed',
      source_signals: ['events'],
    },
  ],
  signal_types_analyzed: ['pod_logs', 'events', 'cluster_info'],
  truncation_notes: null,
  timeline: [
    {
      timestamp: '2024-01-15T13:43:00Z',
      title: 'OOMKilled',
      description: 'Auth-Service pod killed',
      severity: 'critical',
      source: 'events.json',
    },
  ],
}

describe('buildAgentContext', () => {
  it('includes agent instructions at the top', () => {
    const ctx = buildAgentContext(baseReport, [])
    expect(ctx).toContain('You are investigating issues')
    expect(ctx).toContain('Work through the priority actions')
  })

  it('generates priority actions checklist from critical and warning findings', () => {
    const ctx = buildAgentContext(baseReport, [])
    expect(ctx).toContain('## Priority Actions')
    expect(ctx).toContain('1. [ ] [CRITICAL] OOMKilled Pod')
    expect(ctx).toContain('2. [ ] [WARNING] Image Pull Failure')
    // Info findings should NOT appear in priority actions
    expect(ctx).not.toContain('[ ] [INFO]')
  })

  it('includes executive summary under Situation', () => {
    const ctx = buildAgentContext(baseReport, [])
    expect(ctx).toContain('## Situation')
    expect(ctx).toContain('Cluster has OOM issues and disk pressure.')
  })

  it('includes event timeline with timestamps', () => {
    const ctx = buildAgentContext(baseReport, [])
    expect(ctx).toContain('## Event Timeline')
    expect(ctx).toContain('2024-01-15T13:43:00Z')
    expect(ctx).toContain('OOMKilled')
  })

  it('includes findings sorted by severity', () => {
    const ctx = buildAgentContext(baseReport, [])
    const criticalIdx = ctx.indexOf('[CRITICAL]')
    const warningIdx = ctx.indexOf('[WARNING]')
    const infoIdx = ctx.indexOf('[INFO]')
    expect(criticalIdx).toBeLessThan(warningIdx)
    expect(warningIdx).toBeLessThan(infoIdx)
  })

  it('includes evidence with file paths and excerpts', () => {
    const ctx = buildAgentContext(baseReport, [])
    expect(ctx).toContain('`logs/auth-service.log`')
    expect(ctx).toContain('OOMKilled process 1842')
  })

  it('includes remediation commands', () => {
    const ctx = buildAgentContext(baseReport, [])
    expect(ctx).toContain('kubectl edit deployment auth-service')
  })

  it('omits investigation notes when no chat messages exist', () => {
    const ctx = buildAgentContext(baseReport, [])
    expect(ctx).not.toContain('## Investigation Notes')
  })

  it('includes substantive assistant messages as investigation notes', () => {
    const messages: ChatMessage[] = [
      { role: 'user', content: 'What caused the OOM?' },
      { role: 'assistant', content: 'The auth-service session cache is expanding beyond the 512Mi limit. Looking at the pod logs, the process allocates 256MB chunks for cache expansion which pushes it over the memory ceiling.' },
    ]
    const ctx = buildAgentContext(baseReport, messages)
    expect(ctx).toContain('## Investigation Notes')
    expect(ctx).toContain('session cache is expanding')
  })

  it('excludes short assistant messages from investigation notes', () => {
    const messages: ChatMessage[] = [
      { role: 'user', content: 'Thanks' },
      { role: 'assistant', content: 'You are welcome!' },
    ]
    const ctx = buildAgentContext(baseReport, messages)
    expect(ctx).not.toContain('## Investigation Notes')
  })

  it('excludes user messages from investigation notes', () => {
    const messages: ChatMessage[] = [
      { role: 'user', content: 'This is a long user message that exceeds fifty characters for sure and should not appear in the output' },
    ]
    const ctx = buildAgentContext(baseReport, messages)
    expect(ctx).not.toContain('## Investigation Notes')
  })

  it('handles report with no timeline', () => {
    const noTimeline = { ...baseReport, timeline: undefined }
    const ctx = buildAgentContext(noTimeline, [])
    expect(ctx).not.toContain('## Event Timeline')
    expect(ctx).toContain('## Findings')
  })

  it('handles report with only info findings — no priority actions', () => {
    const infoOnly: DiagnosticReport = {
      ...baseReport,
      findings: [baseReport.findings[2]], // just the info finding
    }
    const ctx = buildAgentContext(infoOnly, [])
    expect(ctx).not.toContain('## Priority Actions')
  })
})
