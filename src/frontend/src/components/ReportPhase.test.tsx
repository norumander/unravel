import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ReportPhase } from './ReportPhase'

function createMockSSEResponse(events: Array<{ type: string; [key: string]: unknown }>) {
  const lines = events.map((e) => `data: ${JSON.stringify(e)}`).join('\n') + '\n'
  const encoder = new TextEncoder()

  return {
    ok: true,
    body: {
      getReader() {
        let done = false
        return {
          read() {
            if (done) return Promise.resolve({ done: true, value: undefined })
            done = true
            return Promise.resolve({ done: false, value: encoder.encode(lines) })
          },
        }
      },
    },
  }
}

describe('ReportPhase', () => {
  const mockOnReportComplete = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders report with findings from SSE stream', async () => {
    const report = {
      executive_summary: 'Cluster has critical OOM issues.',
      findings: [
        {
          severity: 'critical',
          title: 'OOMKilled Pod',
          description: 'Pod nginx is being OOM killed repeatedly',
          root_cause: 'Memory limit set to 64Mi is insufficient',
          remediation: 'Increase memory limit to 256Mi',
          source_signals: ['pod_logs', 'events'],
        },
        {
          severity: 'info',
          title: 'Healthy node',
          description: 'Node worker-1 is healthy',
          root_cause: 'N/A',
          remediation: 'No action needed',
          source_signals: ['node_status'],
        },
      ],
      signal_types_analyzed: ['pod_logs', 'events', 'node_status'],
      truncation_notes: null,
    }

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        createMockSSEResponse([
          { type: 'chunk', content: 'analyzing...' },
          { type: 'report', report },
        ]),
      ),
    )

    render(
      <ReportPhase
        sessionId="test-session"
        manifest={{ total_files: 10, total_size_bytes: 5242880, files: [] }}
        signalSummary={{ events: 3, pod_logs: 5 }}
        onReportComplete={mockOnReportComplete}
      />,
    )

    await waitFor(() => {
      expect(screen.getByTestId('report-content')).toBeInTheDocument()
    })

    expect(screen.getByText('Cluster has critical OOM issues.')).toBeInTheDocument()
    expect(screen.getByText('OOMKilled Pod')).toBeInTheDocument()
    expect(mockOnReportComplete).toHaveBeenCalledWith(report)
  })

  it('shows error on SSE error event', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        createMockSSEResponse([{ type: 'error', message: 'API key invalid' }]),
      ),
    )

    render(
      <ReportPhase
        sessionId="test-session"
        manifest={{ total_files: 10, total_size_bytes: 5242880, files: [] }}
        signalSummary={{ events: 3, pod_logs: 5 }}
        onReportComplete={mockOnReportComplete}
      />,
    )

    await waitFor(() => {
      expect(screen.getByTestId('report-error')).toBeInTheDocument()
      expect(screen.getByText('API key invalid')).toBeInTheDocument()
    })
  })
})
