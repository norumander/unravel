import { useCallback, useEffect, useState } from 'react'

interface FileViewerProps {
  sessionId: string
  filePath: string
  onClose: () => void
}

export function FileViewer({ sessionId, filePath, onClose }: FileViewerProps) {
  const [content, setContent] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    setContent(null)

    fetch(`/api/files/${sessionId}/${filePath}`, { signal: controller.signal })
      .then((res) => {
        if (res.status === 404) {
          throw new Error('File not found')
        }
        if (!res.ok) {
          throw new Error(`Failed to load file (${res.status})`)
        }
        return res.text()
      })
      .then((text) => {
        setContent(text)
        setLoading(false)
      })
      .catch((err) => {
        if (err.name === 'AbortError') return
        setError(err.message || 'Failed to load file')
        setLoading(false)
      })

    return () => controller.abort()
  }, [sessionId, filePath])

  const handleEscape = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    },
    [onClose]
  )

  useEffect(() => {
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [handleEscape])

  const handleCopy = useCallback(async () => {
    if (!content) return
    try {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard API may be unavailable; silently ignore
    }
  }, [content])

  const lines = content?.split('\n') ?? []

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
        data-testid="file-viewer-backdrop"
      />

      {/* Panel */}
      <div className="relative flex h-full w-[600px] max-w-full flex-col border-l border-zinc-800 bg-zinc-900">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
          <span className="min-w-0 flex-1 truncate font-mono text-sm text-zinc-200">
            {filePath}
          </span>
          <div className="ml-3 flex items-center gap-1">
            {/* Copy button */}
            <button
              onClick={handleCopy}
              disabled={!content}
              className="p-1 text-zinc-500 hover:text-zinc-300 disabled:opacity-30"
              title="Copy to clipboard"
              aria-label="Copy file content"
              data-testid="copy-button"
            >
              {copied ? (
                <span className="px-1 text-xs text-green-400">Copied!</span>
              ) : (
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
              )}
            </button>

            {/* Close button */}
            <button
              onClick={onClose}
              className="p-1 text-zinc-500 hover:text-zinc-300"
              title="Close"
              aria-label="Close file viewer"
              data-testid="close-button"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        </div>

        {/* Content area */}
        <div className="flex-1 overflow-auto p-4">
          {loading && (
            <div className="flex items-center gap-2 text-sm text-zinc-500" data-testid="loading-indicator">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-zinc-500" />
              Loading...
            </div>
          )}

          {error && (
            <div className="text-sm text-red-400" data-testid="error-message">
              {error}
            </div>
          )}

          {content !== null && (
            <pre className="font-mono text-xs leading-relaxed">
              <table className="border-collapse">
                <tbody>
                  {lines.map((line, i) => (
                    <tr key={i}>
                      <td className="select-none pr-4 text-right align-top text-zinc-600">
                        {i + 1}
                      </td>
                      <td className="whitespace-pre-wrap text-zinc-300">{line}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </pre>
          )}
        </div>
      </div>
    </div>
  )
}
