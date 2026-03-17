import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ChatPhase } from './ChatPhase'

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

describe('ChatPhase', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders chat input and send button', () => {
    render(<ChatPhase sessionId="test-session" report={null} />)
    expect(screen.getByTestId('chat-input')).toBeInTheDocument()
    expect(screen.getByTestId('send-button')).toBeInTheDocument()
  })

  it('sends message and shows response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        createMockSSEResponse([
          { type: 'chunk', content: 'The pod is crash-looping.' },
          { type: 'done' },
        ]),
      ),
    )

    render(<ChatPhase sessionId="test-session" report={null} />)

    const input = screen.getByTestId('chat-input')
    const button = screen.getByTestId('send-button')

    fireEvent.change(input, { target: { value: 'What is wrong?' } })
    fireEvent.click(button)

    await waitFor(() => {
      const messages = screen.getByTestId('chat-messages')
      expect(messages.textContent).toContain('What is wrong?')
      expect(messages.textContent).toContain('The pod is crash-looping.')
    })
  })

  it('shows tool use indicator', async () => {
    // Only send tool_use event — no 'done' event so the indicator stays visible
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        createMockSSEResponse([
          { type: 'tool_use', name: 'get_file_contents', file_path: 'logs/pod.log' },
        ]),
      ),
    )

    render(<ChatPhase sessionId="test-session" report={null} />)

    const input = screen.getByTestId('chat-input')
    fireEvent.change(input, { target: { value: 'Check the logs' } })
    fireEvent.click(screen.getByTestId('send-button'))

    await waitFor(() => {
      expect(screen.getByTestId('tool-indicator')).toBeInTheDocument()
      expect(screen.getByText(/logs\/pod\.log/)).toBeInTheDocument()
    })
  })

  it('shows error from SSE', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        createMockSSEResponse([{ type: 'error', message: 'Rate limit exceeded' }]),
      ),
    )

    render(<ChatPhase sessionId="test-session" report={null} />)

    fireEvent.change(screen.getByTestId('chat-input'), { target: { value: 'hello' } })
    fireEvent.click(screen.getByTestId('send-button'))

    await waitFor(() => {
      expect(screen.getByTestId('chat-error')).toBeInTheDocument()
      expect(screen.getByText('Rate limit exceeded')).toBeInTheDocument()
    })
  })

  it('disables send button when input is empty', () => {
    render(<ChatPhase sessionId="test-session" report={null} />)
    expect(screen.getByTestId('send-button')).toBeDisabled()
  })
})
