import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { UploadPhase } from './UploadPhase'

describe('UploadPhase', () => {
  const mockOnUploadComplete = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the drop zone', () => {
    render(<UploadPhase onUploadComplete={mockOnUploadComplete} />)
    expect(screen.getByTestId('drop-zone')).toBeInTheDocument()
    expect(screen.getByText(/drop a support bundle/i)).toBeInTheDocument()
  })

  it('renders file input', () => {
    render(<UploadPhase onUploadComplete={mockOnUploadComplete} />)
    const input = document.getElementById('file-input') as HTMLInputElement
    expect(input).toBeInTheDocument()
    expect(input.type).toBe('file')
  })

  it('shows error for invalid file type (client-side)', async () => {
    render(<UploadPhase onUploadComplete={mockOnUploadComplete} />)

    const input = document.getElementById('file-input') as HTMLInputElement
    const file = new File(['test'], 'test.txt', { type: 'text/plain' })
    fireEvent.change(input, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByTestId('upload-error')).toBeInTheDocument()
      expect(screen.getByText(/invalid file type/i)).toBeInTheDocument()
    })
  })

  it('shows error on server-side upload failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        json: async () => ({ error: 'Invalid file format. Expected a .tar.gz archive.' }),
      }),
    )

    render(<UploadPhase onUploadComplete={mockOnUploadComplete} />)

    const input = document.getElementById('file-input') as HTMLInputElement
    const file = new File(['test'], 'test.tar.gz', { type: 'application/gzip' })
    fireEvent.change(input, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByTestId('upload-error')).toBeInTheDocument()
      expect(screen.getByText(/invalid file format/i)).toBeInTheDocument()
    })
  })

  it('calls onUploadComplete on successful upload', async () => {
    const mockResponse = {
      session_id: 'test-session',
      manifest: { total_files: 5, total_size_bytes: 1024, files: [] },
      signal_summary: { pod_logs: 3, events: 2 },
    }

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => mockResponse,
      }),
    )

    render(<UploadPhase onUploadComplete={mockOnUploadComplete} />)

    const input = document.getElementById('file-input') as HTMLInputElement
    const file = new File(['test'], 'bundle.tar.gz', { type: 'application/gzip' })
    fireEvent.change(input, { target: { files: [file] } })

    await waitFor(() => {
      expect(mockOnUploadComplete).toHaveBeenCalledWith('test-session', mockResponse.manifest, mockResponse.signal_summary)
    })
  })
})
