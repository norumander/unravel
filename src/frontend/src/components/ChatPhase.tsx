import { useCallback, useRef, useState } from 'react'
import type { ChatMessage, SSEEvent } from '../types/api'
import { useSSE } from '../hooks/useSSE'

interface ChatPhaseProps {
  sessionId: string
}

export function ChatPhase({ sessionId }: ChatPhaseProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [streamingContent, setStreamingContent] = useState('')
  const [toolInProgress, setToolInProgress] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const handleChunk = useCallback((content: string) => {
    setStreamingContent((prev) => prev + content)
  }, [])

  const handleEvent = useCallback((event: SSEEvent) => {
    if (event.type === 'tool_use') {
      setToolInProgress(event.file_path)
    } else if (event.type === 'done') {
      setStreamingContent((prev) => {
        if (prev.trim()) {
          setMessages((msgs) => [...msgs, { role: 'assistant', content: prev }])
        }
        return ''
      })
      setToolInProgress(null)
    }
  }, [])

  const handleDone = useCallback(() => {
    scrollToBottom()
  }, [])

  const { isStreaming, error, startStream } = useSSE({
    onChunk: handleChunk,
    onEvent: handleEvent,
    onDone: handleDone,
  })

  const sendMessage = useCallback(() => {
    const trimmed = input.trim()
    if (!trimmed || isStreaming) return

    setMessages((prev) => [...prev, { role: 'user', content: trimmed }])
    setInput('')
    setStreamingContent('')
    setToolInProgress(null)

    startStream(`/api/chat/${sessionId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: trimmed }),
    })
  }, [input, isStreaming, sessionId, startStream])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="flex h-[500px] flex-col rounded-md border border-gray-200">
      <div className="border-b border-gray-200 px-4 py-2">
        <h2 className="text-sm font-semibold text-gray-700">Investigation Chat</h2>
      </div>

      <div
        data-testid="chat-messages"
        className="flex-1 space-y-4 overflow-y-auto p-4"
      >
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] rounded-lg px-4 py-2 text-sm ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-800'
              }`}
            >
              <pre className="whitespace-pre-wrap font-sans">{msg.content}</pre>
            </div>
          </div>
        ))}

        {streamingContent && (
          <div className="flex justify-start">
            <div className="max-w-[80%] rounded-lg bg-gray-100 px-4 py-2 text-sm text-gray-800">
              <pre className="whitespace-pre-wrap font-sans">{streamingContent}</pre>
            </div>
          </div>
        )}

        {toolInProgress && (
          <div
            data-testid="tool-indicator"
            className="flex items-center gap-2 text-xs text-gray-500"
          >
            <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-amber-500" />
            Retrieving file: {toolInProgress}
          </div>
        )}

        {error && (
          <div
            data-testid="chat-error"
            className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700"
          >
            {error}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div className="border-t border-gray-200 p-3">
        <div className="flex gap-2">
          <textarea
            data-testid="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about the bundle..."
            disabled={isStreaming}
            rows={1}
            className="flex-1 resize-none rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none disabled:opacity-50"
          />
          <button
            data-testid="send-button"
            onClick={sendMessage}
            disabled={isStreaming || !input.trim()}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  )
}
