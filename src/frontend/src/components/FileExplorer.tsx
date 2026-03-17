import { useState, useMemo } from 'react'
import type { BundleFile, BundleManifest } from '../types/api'

interface FileExplorerProps {
  manifest: BundleManifest
  onFileSelect: (path: string) => void
}

const SIGNAL_CONFIG: Record<string, { label: string; color: string }> = {
  events: { label: 'Events', color: 'bg-amber-400' },
  pod_logs: { label: 'Pod Logs', color: 'bg-blue-400' },
  cluster_info: { label: 'Cluster Info', color: 'bg-emerald-400' },
  resource_definitions: { label: 'Resources', color: 'bg-purple-400' },
  node_status: { label: 'Node Status', color: 'bg-cyan-400' },
  other: { label: 'Other', color: 'bg-zinc-400' },
}

const SIGNAL_ORDER = [
  'events',
  'pod_logs',
  'cluster_info',
  'resource_definitions',
  'node_status',
  'other',
]

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
}

function truncatePath(path: string): string {
  const segments = path.split('/')
  if (segments.length <= 2) return path
  return segments.slice(-2).join('/')
}

export default function FileExplorer({
  manifest,
  onFileSelect,
}: FileExplorerProps) {
  const grouped = useMemo(() => {
    const groups: Record<string, BundleFile[]> = {}
    for (const file of manifest.files) {
      const key = file.signal_type in SIGNAL_CONFIG ? file.signal_type : 'other'
      if (!groups[key]) groups[key] = []
      groups[key].push(file)
    }
    return groups
  }, [manifest.files])

  const initialExpanded = useMemo(() => {
    const set = new Set<string>()
    if (grouped['events'] && grouped['events'].length > 0) {
      set.add('events')
    }
    return set
    // Only compute once on mount based on initial grouped value
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const [expanded, setExpanded] = useState<Set<string>>(initialExpanded)

  function toggleGroup(signalType: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(signalType)) {
        next.delete(signalType)
      } else {
        next.add(signalType)
      }
      return next
    })
  }

  const orderedGroups = useMemo(() => {
    const ordered: { key: string; files: BundleFile[] }[] = []
    for (const key of SIGNAL_ORDER) {
      if (grouped[key] && grouped[key].length > 0) {
        ordered.push({ key, files: grouped[key] })
      }
    }
    // Include any signal types not in SIGNAL_ORDER under "other"
    for (const key of Object.keys(grouped)) {
      if (!SIGNAL_ORDER.includes(key) && grouped[key].length > 0) {
        const existing = ordered.find((g) => g.key === 'other')
        if (existing) {
          existing.files = [...existing.files, ...grouped[key]]
        } else {
          ordered.push({ key: 'other', files: grouped[key] })
        }
      }
    }
    return ordered
  }, [grouped])

  return (
    <div className="space-y-0.5">
      {orderedGroups.map(({ key, files }) => {
        const config = SIGNAL_CONFIG[key] ?? SIGNAL_CONFIG.other
        const isExpanded = expanded.has(key)
        const totalSize = files.reduce((sum, f) => sum + f.size_bytes, 0)

        return (
          <div key={key}>
            <button
              type="button"
              onClick={() => toggleGroup(key)}
              aria-expanded={isExpanded}
              className="text-zinc-300 text-sm font-medium hover:bg-zinc-800/60 px-3 py-2 cursor-pointer flex items-center gap-2 w-full text-left"
            >
              <svg
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                className={`h-4 w-4 shrink-0 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
              >
                <path d="M6 4l4 4-4 4" />
              </svg>
              <span className={`h-2 w-2 rounded-full shrink-0 ${config.color}`} />
              <span className="truncate">{config.label}</span>
              <span className="text-zinc-500 text-xs ml-auto shrink-0">
                {files.length} {files.length === 1 ? 'file' : 'files'} &middot; {formatSize(totalSize)}
              </span>
            </button>

            {isExpanded && (
              <div>
                {files.map((file) => (
                  <button
                    key={file.path}
                    type="button"
                    onClick={() => onFileSelect(file.path)}
                    className="text-zinc-400 text-xs font-mono hover:bg-zinc-800/60 pl-8 pr-3 py-1.5 cursor-pointer flex items-center justify-between gap-2 w-full text-left"
                  >
                    <span className="truncate">{truncatePath(file.path)}</span>
                    <span className="text-zinc-500 shrink-0">{formatSize(file.size_bytes)}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
