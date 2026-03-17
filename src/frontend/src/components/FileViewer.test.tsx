import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { FileViewer } from './FileViewer'

describe('FileViewer', () => {
  const mockOnClose = vi.fn()
  const defaultProps = {
    sessionId: 'test-session-123',
    filePath: 'events/events.json',
    onClose: mockOnClose,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.restoreAllMocks()
  })

  it('shows loading state initially', () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockReturnValue(new Promise(() => {})), // never resolves
    )

    render(<FileViewer {...defaultProps} />)

    expect(screen.getByTestId('loading-indicator')).toBeInTheDocument()
    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })

  it('displays file content after successful fetch', async () => {
    const fileContent = '{"kind": "EventList", "items": []}'

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        text: async () => fileContent,
      }),
    )

    render(<FileViewer {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByText(fileContent)).toBeInTheDocument()
    })

    // Loading indicator should be gone
    expect(screen.queryByTestId('loading-indicator')).not.toBeInTheDocument()
  })

  it('shows error on 404 response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        text: async () => 'Not Found',
      }),
    )

    render(<FileViewer {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByTestId('error-message')).toBeInTheDocument()
      expect(screen.getByText('File not found')).toBeInTheDocument()
    })
  })

  it('shows error on non-404 failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        text: async () => 'Server Error',
      }),
    )

    render(<FileViewer {...defaultProps} />)

    await waitFor(() => {
      expect(screen.getByTestId('error-message')).toBeInTheDocument()
      expect(screen.getByText('Failed to load file (500)')).toBeInTheDocument()
    })
  })

  it('calls onClose when close button is clicked', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        text: async () => 'file content',
      }),
    )

    render(<FileViewer {...defaultProps} />)

    const closeButton = screen.getByTestId('close-button')
    fireEvent.click(closeButton)

    expect(mockOnClose).toHaveBeenCalledTimes(1)
  })

  it('calls onClose on Escape key press', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        text: async () => 'file content',
      }),
    )

    render(<FileViewer {...defaultProps} />)

    fireEvent.keyDown(document, { key: 'Escape' })

    expect(mockOnClose).toHaveBeenCalledTimes(1)
  })

  it('calls onClose when backdrop is clicked', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        text: async () => 'file content',
      }),
    )

    render(<FileViewer {...defaultProps} />)

    const backdrop = screen.getByTestId('file-viewer-backdrop')
    fireEvent.click(backdrop)

    expect(mockOnClose).toHaveBeenCalledTimes(1)
  })

  it('copy button copies content to clipboard', async () => {
    const fileContent = 'line one\nline two'
    const mockWriteText = vi.fn().mockResolvedValue(undefined)

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        text: async () => fileContent,
      }),
    )

    Object.assign(navigator, {
      clipboard: { writeText: mockWriteText },
    })

    render(<FileViewer {...defaultProps} />)

    // Wait for content to load
    await waitFor(() => {
      expect(screen.getByText('line one')).toBeInTheDocument()
    })

    const copyButton = screen.getByTestId('copy-button')
    fireEvent.click(copyButton)

    await waitFor(() => {
      expect(mockWriteText).toHaveBeenCalledWith(fileContent)
    })
  })

  it('displays the file path in the header', () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockReturnValue(new Promise(() => {})),
    )

    render(<FileViewer {...defaultProps} />)

    expect(screen.getByText('events/events.json')).toBeInTheDocument()
  })

  it('fetches the correct API URL', () => {
    const mockFetch = vi.fn().mockReturnValue(new Promise(() => {}))
    vi.stubGlobal('fetch', mockFetch)

    render(<FileViewer {...defaultProps} />)

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/files/test-session-123/events/events.json',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
  })
})
