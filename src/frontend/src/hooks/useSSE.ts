import { useCallback, useRef, useState } from 'react'
import type { SSEEvent } from '../types/api'

interface UseSSEOptions {
  onChunk?: (content: string) => void
  onEvent?: (event: SSEEvent) => void
  onError?: (message: string) => void
  onDone?: () => void
}

interface UseSSEReturn {
  isStreaming: boolean
  error: string | null
  startStream: (url: string, options?: RequestInit) => void
  stopStream: () => void
}

export function useSSE({ onChunk, onEvent, onError, onDone }: UseSSEOptions = {}): UseSSEReturn {
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const stopStream = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setIsStreaming(false)
  }, [])

  const startStream = useCallback(
    (url: string, fetchOptions?: RequestInit) => {
      stopStream()
      setError(null)
      setIsStreaming(true)

      const controller = new AbortController()
      abortRef.current = controller

      fetch(url, {
        ...fetchOptions,
        signal: controller.signal,
        headers: {
          ...fetchOptions?.headers,
          Accept: 'text/event-stream',
        },
      })
        .then(async (response) => {
          if (!response.ok) {
            const body = await response.json().catch(() => ({ error: 'Request failed' }))
            throw new Error(body.error || `HTTP ${response.status}`)
          }

          const reader = response.body?.getReader()
          if (!reader) throw new Error('No response body')

          const decoder = new TextDecoder()
          let buffer = ''

          while (true) {
            const { done, value } = await reader.read()
            if (done) break

            buffer += decoder.decode(value, { stream: true })
            const lines = buffer.split('\n')
            buffer = lines.pop() || ''

            for (const line of lines) {
              const trimmed = line.trim()
              if (!trimmed.startsWith('data:')) continue

              const dataStr = trimmed.slice(5).trim()
              if (!dataStr || dataStr === '[DONE]') continue

              try {
                const event: SSEEvent = JSON.parse(dataStr)
                onEvent?.(event)

                switch (event.type) {
                  case 'chunk':
                    onChunk?.(event.content)
                    break
                  case 'error':
                    setError(event.message)
                    onError?.(event.message)
                    break
                  case 'done':
                    onDone?.()
                    break
                }
              } catch {
                // Skip non-JSON lines
              }
            }
          }
        })
        .catch((err) => {
          if (err.name !== 'AbortError') {
            const msg = err.message || 'Stream connection failed'
            setError(msg)
            onError?.(msg)
          }
        })
        .finally(() => {
          setIsStreaming(false)
          abortRef.current = null
        })
    },
    [onChunk, onEvent, onError, onDone, stopStream],
  )

  return { isStreaming, error, startStream, stopStream }
}
