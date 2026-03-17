import { useCallback, useEffect, useRef, useState } from 'react'
import type { ChatMessage, DiagnosticReport, SSEEvent } from '../types/api'
import { useSSE } from '../hooks/useSSE'

interface ChatPhaseProps {
  sessionId: string
  report: DiagnosticReport | null
}

function generateSuggestions(report: DiagnosticReport): string[] {
  const suggestions: string[] = []
  const critical = report.findings.filter(f => f.severity === 'critical')
  const warnings = report.findings.filter(f => f.severity === 'warning')

  if (critical.length > 0) {
    suggestions.push(`What caused "${critical[0].title}" and how do I fix it?`)
  }
  if (critical.length > 1) {
    suggestions.push(`Are the issues "${critical[0].title}" and "${critical[1].title}" related?`)
  }
  if (warnings.length > 0) {
    suggestions.push(`Tell me more about the warning: "${warnings[0].title}"`)
  }
  suggestions.push('What kubectl commands should I run to diagnose these issues?')

  return suggestions.slice(0, 4)
}

export function ChatPhase({ sessionId, report }: ChatPhaseProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [streamingContent, setStreamingContent] = useState('')
  const [toolInProgress, setToolInProgress] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const pendingContentRef = useRef('')

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  const handleChunk = useCallback((content: string) => {
    pendingContentRef.current += content
    setStreamingContent((prev) => prev + content)
  }, [])

  const handleEvent = useCallback((event: SSEEvent) => {
    if (event.type === 'tool_use') {
      setToolInProgress(event.file_path)
    } else if (event.type === 'done') {
      const content = pendingContentRef.current
      if (content.trim()) {
        setMessages((msgs) => [...msgs, { role: 'assistant', content }])
      }
      setStreamingContent('')
      setToolInProgress(null)
      pendingContentRef.current = ''
    }
  }, [])

  const { isStreaming, error, startStream } = useSSE({
    onChunk: handleChunk,
    onEvent: handleEvent,
    onDone: scrollToBottom,
  })

  // Auto-scroll during streaming
  useEffect(() => {
    if (streamingContent) scrollToBottom()
  }, [streamingContent, scrollToBottom])

  const sendMessage = useCallback(
    (text?: string) => {
      const trimmed = (text ?? input).trim()
      if (!trimmed || isStreaming) return

      setMessages((prev) => [...prev, { role: 'user', content: trimmed }])
      setInput('')
      setStreamingContent('')
      setToolInProgress(null)
      pendingContentRef.current = ''

      startStream(`/api/chat/${sessionId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: trimmed }),
      })
    },
    [input, isStreaming, sessionId, startStream],
  )

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const handleSuggestionClick = (question: string) => {
    setInput(question)
    sendMessage(question)
  }

  const suggestions = report ? generateSuggestions(report) : []

  return (
    <div className="flex h-[480px] flex-col rounded-xl border border-zinc-800 bg-zinc-900">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-zinc-800 px-5 py-3">
        <svg
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          className="h-4 w-4 text-zinc-500"
        >
          <rect x="2" y="3" width="12" height="10" rx="1.5" />
          <path d="M5 8l2 2 4-4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <h2 className="text-sm font-semibold text-zinc-300">Investigation Chat</h2>
      </div>

      {/* Messages area */}
      <div
        data-testid="chat-messages"
        className="flex-1 space-y-5 overflow-y-auto p-5"
      >
        {/* Suggested questions when no messages yet */}
        {messages.length === 0 && report && suggestions.length > 0 && (
          <div data-testid="suggested-questions">
            <p className="mb-3 text-xs text-zinc-500">Suggested questions</p>
            <div className="space-y-2">
              {suggestions.map((question, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSuggestionClick(question)}
                  className="w-full cursor-pointer rounded-lg border border-zinc-700 px-4 py-3 text-left text-sm text-zinc-300 transition-colors hover:border-zinc-600 hover:bg-zinc-800"
                >
                  {question}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Message history */}
        {messages.map((msg, idx) =>
          msg.role === 'user' ? (
            <div key={`${msg.role}-${idx}`} className="flex justify-end">
              <div className="ml-16 rounded-xl bg-zinc-700/50 px-4 py-3 text-sm text-zinc-100">
                <pre className="whitespace-pre-wrap font-sans">{msg.content}</pre>
              </div>
            </div>
          ) : (
            <div key={`${msg.role}-${idx}`} className="mr-8">
              <p className="mb-1 text-xs font-medium text-zinc-500">Unravel</p>
              <div className="text-sm leading-relaxed text-zinc-300">
                <pre className="whitespace-pre-wrap font-sans">{msg.content}</pre>
              </div>
            </div>
          ),
        )}

        {/* Streaming content */}
        {streamingContent && (
          <div className="mr-8">
            <p className="mb-1 text-xs font-medium text-zinc-500">Unravel</p>
            <div className="text-sm leading-relaxed text-zinc-300">
              <pre className="whitespace-pre-wrap font-sans">
                {streamingContent}
                <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-blue-400 align-text-bottom" />
              </pre>
            </div>
          </div>
        )}

        {/* Tool use indicator */}
        {toolInProgress && (
          <div
            data-testid="tool-indicator"
            role="status"
            aria-label={`Retrieving file: ${toolInProgress}`}
            className="flex items-center gap-2 rounded-lg bg-zinc-800/80 px-3 py-2 font-mono text-xs text-zinc-400"
          >
            <span className="h-2 w-2 animate-pulse rounded-full bg-amber-500" />
            Reading {toolInProgress}
          </div>
        )}

        {/* Error state */}
        {error && (
          <div
            data-testid="chat-error"
            className="rounded-lg border border-red-900/30 bg-red-950/50 px-4 py-2 text-sm text-red-400"
          >
            {error}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="border-t border-zinc-800 p-4">
        <div className="relative">
          <textarea
            data-testid="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about the bundle..."
            disabled={isStreaming}
            rows={1}
            className="w-full resize-none rounded-xl border border-zinc-700 bg-zinc-800 px-4 py-3 pr-12 text-sm text-zinc-100 placeholder-zinc-500 focus:border-blue-500 focus:outline-none disabled:opacity-50"
          />
          <button
            data-testid="send-button"
            onClick={() => sendMessage()}
            disabled={isStreaming || !input.trim()}
            className="absolute bottom-2 right-2 rounded-lg bg-blue-600 p-2 text-white transition-colors hover:bg-blue-500 disabled:opacity-30 disabled:hover:bg-blue-600"
          >
            <svg
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className="h-4 w-4"
            >
              <path
                d="M8 12V4m0 0L4 8m4-4l4 4"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        </div>
      </div>
    </div>
  )
}
