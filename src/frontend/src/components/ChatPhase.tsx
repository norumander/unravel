import { useCallback, useEffect, useRef, useState } from 'react'
import type { ChatMessage, DiagnosticReport, LLMMeta, SSEEvent } from '../types/api'
import { useSSE } from '../hooks/useSSE'

interface ChatPhaseProps {
  sessionId: string
  report: DiagnosticReport | null
  onToast?: (type: 'warning' | 'error', message: string) => void
  onMessagesChange?: (messages: ChatMessage[]) => void
}

function generateSuggestions(report: DiagnosticReport): string[] {
  const suggestions: string[] = []
  const critical = report.findings.filter((f) => f.severity === 'critical')
  const warnings = report.findings.filter((f) => f.severity === 'warning')

  if (critical.length > 0) {
    suggestions.push(`What caused "${critical[0].title}" and how do I fix it?`)
  }
  if (critical.length > 1) {
    suggestions.push(
      `Are the issues "${critical[0].title}" and "${critical[1].title}" related?`,
    )
  }
  if (warnings.length > 0) {
    suggestions.push(`Tell me more about the warning: "${warnings[0].title}"`)
  }
  suggestions.push('What kubectl commands should I run to diagnose these issues?')

  return suggestions.slice(0, 4)
}

// --- Markdown rendering ---

interface Section {
  heading: string | null
  content: string
}

/** Split text on ## headings into sections */
function splitSections(text: string): Section[] {
  const lines = text.split('\n')
  const sections: Section[] = []
  let currentHeading: string | null = null
  let currentLines: string[] = []

  for (const line of lines) {
    const headingMatch = line.match(/^#{1,3}\s+(.+)$/)
    if (headingMatch) {
      // Flush previous section
      if (currentLines.length > 0 || currentHeading !== null) {
        sections.push({ heading: currentHeading, content: currentLines.join('\n') })
      }
      currentHeading = headingMatch[1].trim()
      currentLines = []
    } else {
      currentLines.push(line)
    }
  }
  // Flush last section
  if (currentLines.length > 0 || currentHeading !== null) {
    sections.push({ heading: currentHeading, content: currentLines.join('\n') })
  }

  return sections
}

/** Render a full assistant message with section containers */
function FormattedContent({ text }: { text: string }) {
  const sections = splitSections(text)

  // If there's only one section with no heading, render flat (no container)
  if (sections.length === 1 && sections[0].heading === null) {
    return <RichText text={sections[0].content} />
  }

  return (
    <div className="space-y-3">
      {sections.map((section, i) => {
        const trimmed = section.content.trim()
        if (!trimmed && !section.heading) return null

        // Sections without heading (preamble text before first ##)
        if (section.heading === null) {
          return <RichText key={i} text={trimmed} />
        }

        // Section with heading — render in a container
        return (
          <div key={i} className="rounded-lg border-l-2 border-teal-500/30 bg-zinc-800/50 pl-0">
            <div className="px-4 pt-3 pb-1">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
                {section.heading}
              </h4>
            </div>
            {trimmed && (
              <div className="px-4 py-3">
                <RichText text={trimmed} />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

/** Render rich text: code blocks, then inline formatting */
function RichText({ text }: { text: string }) {
  const parts: React.ReactNode[] = []
  const codeBlockRegex = /```(\w*)\n?([\s\S]*?)```/g
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = codeBlockRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(
        <InlineFormattedText key={`t-${lastIndex}`} text={text.slice(lastIndex, match.index)} />,
      )
    }
    parts.push(
      <pre
        key={`c-${match.index}`}
        className="my-2 overflow-x-auto rounded-lg border border-zinc-700 bg-zinc-950 p-3 font-mono text-xs leading-relaxed text-zinc-300"
      >
        {match[2].trim()}
      </pre>,
    )
    lastIndex = match.index + match[0].length
  }

  if (lastIndex < text.length) {
    parts.push(<InlineFormattedText key={`t-${lastIndex}`} text={text.slice(lastIndex)} />)
  }

  return <div className="space-y-1">{parts}</div>
}

/** Handle inline code, bold, and paragraph breaks */
function InlineFormattedText({ text }: { text: string }) {
  const paragraphs = text.split(/\n{2,}/)
  return (
    <>
      {paragraphs.map((para, pi) => {
        const trimmed = para.trim()
        if (!trimmed) return null

        // Detect bold-only lines as sub-headers (e.g. "**STEP 1: DO SOMETHING**")
        const boldLineMatch = trimmed.match(/^\*\*(.+)\*\*$/)
        if (boldLineMatch) {
          return (
            <h5
              key={pi}
              className="mt-4 mb-1 text-sm font-semibold text-zinc-200 first:mt-0"
            >
              {boldLineMatch[1]}
            </h5>
          )
        }

        // Detect lines starting with bold label then content (e.g. "**Root Cause:** The pod...")
        // These render the label as a mini sub-header
        const boldPrefixMatch = trimmed.match(/^\*\*(.+?)\*\*[:\s]\s*(.+)/)
        if (boldPrefixMatch && boldPrefixMatch[1].length < 60) {
          return (
            <div key={pi} className="mt-3 first:mt-0">
              <span className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
                {boldPrefixMatch[1].replace(/:$/, '')}
              </span>
              <p className="mt-0.5 leading-relaxed">
                {formatInline(boldPrefixMatch[2])}
              </p>
            </div>
          )
        }

        // Detect list blocks (lines starting with "- " or "1. ")
        const lines = trimmed.split('\n')
        const isListBlock = lines.length > 1 && lines.every((l) => /^(\d+\.\s|[-*]\s)/.test(l.trim()))
        if (isListBlock) {
          const isOrdered = /^\d+\./.test(lines[0].trim())
          const Tag = isOrdered ? 'ol' : 'ul'
          return (
            <Tag
              key={pi}
              className={`space-y-1 leading-relaxed ${isOrdered ? 'list-decimal' : 'list-disc'} ml-4`}
            >
              {lines.map((line, li) => (
                <li key={li} className="pl-1">
                  {formatInline(line.replace(/^(\d+\.\s|[-*]\s)/, ''))}
                </li>
              ))}
            </Tag>
          )
        }

        return (
          <p key={pi} className="leading-relaxed">
            {formatInline(trimmed)}
          </p>
        )
      })}
    </>
  )
}

function formatInline(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = []
  const regex = /(\*\*(.+?)\*\*|`([^`]+)`|\n)/g
  let lastIdx = 0
  let m: RegExpExecArray | null

  while ((m = regex.exec(text)) !== null) {
    if (m.index > lastIdx) {
      parts.push(text.slice(lastIdx, m.index))
    }
    if (m[0] === '\n') {
      parts.push(<br key={`br-${m.index}`} />)
    } else if (m[2]) {
      parts.push(
        <strong key={`b-${m.index}`} className="font-semibold text-zinc-100">
          {m[2]}
        </strong>,
      )
    } else if (m[3]) {
      parts.push(
        <code
          key={`ic-${m.index}`}
          className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-xs text-amber-300"
        >
          {m[3]}
        </code>,
      )
    }
    lastIdx = m.index + m[0].length
  }
  if (lastIdx < text.length) {
    parts.push(text.slice(lastIdx))
  }
  return parts
}

// --- Chat component ---

export function ChatPhase({ sessionId, report, onToast, onMessagesChange }: ChatPhaseProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [streamingContent, setStreamingContent] = useState('')
  const [toolInProgress, setToolInProgress] = useState<string | null>(null)
  const [usedSuggestions, setUsedSuggestions] = useState<Set<string>>(new Set())
  const [suggestionsHidden, setSuggestionsHidden] = useState(false)
  const [lastMeta, setLastMeta] = useState<LLMMeta | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const pendingContentRef = useRef('')

  const scrollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const scrollToBottom = useCallback(() => {
    // Throttle scroll-to-bottom to avoid jitter during fast streaming
    if (scrollTimerRef.current) return
    scrollTimerRef.current = setTimeout(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      scrollTimerRef.current = null
    }, 150)
  }, [])

  const handleChunk = useCallback((content: string) => {
    pendingContentRef.current += content
    setStreamingContent((prev) => prev + content)
  }, [])

  const handleEvent = useCallback((event: SSEEvent) => {
    if (event.type === 'tool_use') {
      setToolInProgress(event.file_path)
    } else if (event.type === 'llm_meta') {
      const { type: _, ...meta } = event
      setLastMeta(meta as LLMMeta)
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
    onWarning: useCallback((msg: string) => onToast?.('warning', msg), [onToast]),
    onError: useCallback((msg: string) => onToast?.('error', msg), [onToast]),
    onDone: scrollToBottom,
  })

  useEffect(() => {
    if (streamingContent) scrollToBottom()
  }, [streamingContent, scrollToBottom])

  useEffect(() => {
    onMessagesChange?.(messages)
  }, [messages, onMessagesChange])

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
    setUsedSuggestions((prev) => new Set(prev).add(question))
    sendMessage(question)
  }

  const allSuggestions = report ? generateSuggestions(report) : []
  const remainingSuggestions = allSuggestions.filter((s) => !usedSuggestions.has(s))
  const showSuggestions = !suggestionsHidden && remainingSuggestions.length > 0 && !isStreaming

  return (
    <div className="flex flex-col rounded-xl border border-zinc-800 bg-zinc-900" style={{ maxHeight: 'calc(100vh - 8rem)' }}>
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
      <div data-testid="chat-messages" className="flex-1 space-y-5 overflow-y-auto p-5" style={{ overscrollBehavior: 'contain' }}>
        {/* Empty state */}
        {messages.length === 0 && !showSuggestions && (
          <p className="py-8 text-center text-sm text-zinc-600">
            Ask follow-up questions — the AI can retrieve and analyze specific files from the bundle.
          </p>
        )}

        {/* Full-size suggestions when no messages yet */}
        {messages.length === 0 && showSuggestions && (
          <div data-testid="suggested-questions">
            <p className="mb-3 text-xs text-zinc-500">Suggested questions</p>
            <div className="space-y-2">
              {remainingSuggestions.map((question, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSuggestionClick(question)}
                  className={`w-full cursor-pointer rounded-lg border px-4 py-3 text-left text-sm transition-colors hover:border-zinc-600 hover:bg-zinc-800 ${
                    idx === 0
                      ? 'border-teal-500/30 bg-teal-500/5 text-zinc-200'
                      : 'border-zinc-700 text-zinc-300'
                  }`}
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
            <div key={`${msg.role}-${idx}`} className="animate-fade-in-up flex justify-end">
              <div className="ml-16 rounded-xl bg-zinc-700/50 px-4 py-3 text-sm text-zinc-100">
                {msg.content}
              </div>
            </div>
          ) : (
            <div key={`${msg.role}-${idx}`} className="animate-fade-in-up">
              <p className="mb-2 text-xs font-medium text-zinc-500">Unravel</p>
              <div className="text-sm text-zinc-300">
                <FormattedContent text={msg.content} />
              </div>
            </div>
          ),
        )}

        {/* Streaming content */}
        {streamingContent && (
          <div>
            <p className="mb-2 text-xs font-medium text-zinc-500">Unravel</p>
            <div className="text-sm text-zinc-300">
              <FormattedContent text={streamingContent} />
              <span className="ml-0.5 inline-block h-4 w-px animate-pulse bg-teal-400 align-text-bottom" />
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

        <div ref={messagesEndRef} style={{ overflowAnchor: 'auto', height: 1 }} />
      </div>

      {/* Suggestion chips + input — unified bottom zone */}
      {messages.length > 0 && showSuggestions && (
        <div className="flex items-start gap-2 px-4 pt-3 pb-1">
          <div data-testid="suggestion-chips" className="flex flex-1 flex-wrap gap-1.5">
            {remainingSuggestions.map((question, idx) => (
              <button
                key={idx}
                onClick={() => handleSuggestionClick(question)}
                className="rounded-full border border-zinc-700 px-3 py-1 text-xs text-zinc-400 transition-colors hover:border-zinc-600 hover:bg-zinc-800 hover:text-zinc-300"
              >
                {question.length > 50 ? question.slice(0, 50) + '\u2026' : question}
              </button>
            ))}
          </div>
          <button
            onClick={() => setSuggestionsHidden(true)}
            className="mt-0.5 flex-shrink-0 p-0.5 text-zinc-600 hover:text-zinc-400"
            aria-label="Dismiss suggestions"
            title="Dismiss suggestions"
          >
            <svg
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className="h-3 w-3"
            >
              <path d="M4 4l8 8M12 4l-8 8" strokeLinecap="round" />
            </svg>
          </button>
        </div>
      )}

      {/* LLM metrics */}
      {lastMeta && !isStreaming && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-teal-500/10 bg-teal-500/[0.02] px-5 py-2 text-[10px]">
          <span className="font-semibold uppercase tracking-widest text-teal-500/60">
            {lastMeta.provider}
          </span>
          <span className="font-mono text-zinc-300">{lastMeta.model}</span>
          <span className="font-mono text-zinc-400">
            {lastMeta.input_tokens.toLocaleString()}+{lastMeta.output_tokens.toLocaleString()} tok
          </span>
          <span className="font-mono text-zinc-400">
            {(lastMeta.latency_ms / 1000).toFixed(1)}s
          </span>
          {lastMeta.used_fallback && (
            <span className="rounded-full bg-amber-500/10 px-1.5 py-0.5 font-semibold uppercase tracking-wide text-amber-400">
              fallback
            </span>
          )}
        </div>
      )}

      {/* Input area */}
      <div className="border-t border-zinc-800 p-4">
        {suggestionsHidden && remainingSuggestions.length > 0 && !isStreaming && (
          <button
            onClick={() => setSuggestionsHidden(false)}
            className="mb-2 text-xs text-zinc-500 hover:text-teal-400 transition-colors"
          >
            Show suggested questions
          </button>
        )}
        <div className="relative">
          <textarea
            data-testid="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about the bundle..."
            disabled={isStreaming}
            rows={1}
            className="w-full resize-none rounded-xl border border-zinc-700 bg-zinc-800 px-4 py-3 pr-12 text-sm text-zinc-100 placeholder-zinc-500 focus:border-teal-500 focus:outline-none disabled:opacity-50"
          />
          <button
            data-testid="send-button"
            onClick={() => sendMessage()}
            disabled={isStreaming || !input.trim()}
            className="absolute bottom-2 right-2 rounded-lg bg-teal-600 p-2 text-white transition-colors hover:bg-teal-500 hover:shadow-lg hover:shadow-teal-500/10 disabled:opacity-30 disabled:hover:bg-teal-600"
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
