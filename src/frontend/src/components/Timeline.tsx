import type { TimelineEvent } from '../types/api'

interface TimelineProps {
  events: TimelineEvent[]
}

const SEVERITY_DOT = {
  critical: 'border-red-500 bg-red-500/20',
  warning: 'border-amber-500 bg-amber-500/20',
  info: 'border-zinc-500 bg-zinc-500/20',
} as const

const SEVERITY_TEXT = {
  critical: 'text-red-400',
  warning: 'text-amber-400',
  info: 'text-zinc-400',
} as const

function formatTimestamp(ts: string): string {
  // Try to parse as ISO date, otherwise return as-is
  try {
    const date = new Date(ts)
    if (isNaN(date.getTime())) return ts
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    })
  } catch {
    return ts
  }
}

export function Timeline({ events }: TimelineProps) {
  if (events.length === 0) return null

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
      <h3 className="mb-4 text-xs font-medium uppercase tracking-wider text-zinc-500">
        Event Timeline
      </h3>

      <div className="relative ml-3">
        {/* Vertical line */}
        <div className="absolute left-0 top-1 bottom-1 w-px bg-zinc-800" />

        <div className="space-y-4" role="list">
          {events.map((event, idx) => (
            <div key={idx} role="listitem" className="relative flex gap-4 pl-6">
              {/* Dot on the line */}
              <div
                className={`absolute left-0 top-1.5 h-3 w-3 -translate-x-1/2 rounded-full border-2 ${SEVERITY_DOT[event.severity]}`}
              />

              {/* Content */}
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2">
                  <span className="tabular-nums font-mono text-xs text-zinc-500">
                    {formatTimestamp(event.timestamp)}
                  </span>
                  <span
                    className={`text-xs font-semibold uppercase ${SEVERITY_TEXT[event.severity]}`}
                  >
                    {event.severity}
                  </span>
                </div>
                <p className="mt-0.5 text-sm font-medium text-zinc-200">{event.title}</p>
                <p className="mt-0.5 text-xs text-zinc-400">{event.description}</p>
                <p className="mt-0.5 font-mono text-xs text-zinc-600">{event.source}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
