import { useCallback, useEffect, useState } from 'react'
import type { SessionDetail as SessionDetailType } from '../types/api'

interface SessionDetailProps {
  sessionId: string
  onClose: () => void
  onOpenReport: (detail: SessionDetailType) => void
  onDelete: (sessionId: string) => void
}

export function SessionDetail({ sessionId, onClose, onOpenReport, onDelete }: SessionDetailProps) {
  const [detail, setDetail] = useState<SessionDetailType | null>(null)
  const [loading, setLoading] = useState(true)
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [showObservability, setShowObservability] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetch(`/api/history/${sessionId}`)
      .then(r => r.json())
      .then(data => {
        if (!cancelled) {
          setDetail(data)
          setNotes(data.summary.notes || '')
          setLoading(false)
        }
      })
      .catch(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [sessionId])

  const handleSaveNotes = useCallback(async () => {
    setSaving(true)
    try {
      await fetch(`/api/history/${sessionId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes }),
      })
    } finally {
      setSaving(false)
    }
  }, [sessionId, notes])

  const handleDelete = useCallback(async () => {
    if (!confirm('Delete this session? This cannot be undone.')) return
    await fetch(`/api/history/${sessionId}`, { method: 'DELETE' })
    onDelete(sessionId)
  }, [sessionId, onDelete])

  if (loading) {
    return (
      <div className="w-[340px] bg-zinc-900 border-l border-zinc-800 p-4 flex items-center justify-center">
        <span className="text-zinc-500 text-sm">Loading...</span>
      </div>
    )
  }

  if (!detail) return null

  const { summary } = detail
  const meta = summary.bundle_metadata

  return (
    <div className="w-[340px] bg-zinc-900 border-l border-zinc-800 p-4 overflow-y-auto flex flex-col">
      {/* Header */}
      <div className="flex justify-between items-start mb-4">
        <div className="flex-1 min-w-0">
          <div className="text-zinc-100 font-mono text-sm font-semibold truncate">
            {summary.bundle_name}
          </div>
          <div className="text-zinc-500 text-[10px] mt-1">
            Analyzed {new Date(summary.timestamp).toLocaleString()} · {(summary.file_size / 1024 / 1024).toFixed(1)} MB
          </div>
        </div>
        <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 ml-2 text-lg">✕</button>
      </div>

      {/* Notes */}
      <div className="mb-4">
        <div className="text-zinc-500 text-[9px] uppercase tracking-widest mb-1">Notes</div>
        <textarea
          value={notes}
          onChange={e => setNotes(e.target.value)}
          onBlur={handleSaveNotes}
          placeholder="Add context: customer, ticket number, cluster..."
          className="w-full bg-zinc-950 border border-zinc-800 rounded-md p-2 text-xs text-zinc-300 placeholder-zinc-600 resize-none focus:outline-none focus:border-zinc-600"
          rows={3}
        />
        {saving && <div className="text-[9px] text-zinc-500 mt-1">Saving...</div>}
      </div>

      {/* Bundle metadata */}
      {meta && (meta.cluster || meta.k8s_version || meta.node_count || meta.namespaces.length > 0) && (
        <div className="mb-4">
          <div className="text-zinc-500 text-[9px] uppercase tracking-widest mb-2">Bundle Metadata</div>
          <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
            {meta.cluster && <>
              <span className="text-zinc-500">Cluster</span>
              <span className="text-zinc-300 font-mono">{meta.cluster}</span>
            </>}
            {meta.node_count != null && <>
              <span className="text-zinc-500">Nodes</span>
              <span className="text-zinc-300">{meta.node_count}</span>
            </>}
            {meta.namespaces.length > 0 && <>
              <span className="text-zinc-500">Namespaces</span>
              <span className="text-zinc-300 font-mono">{meta.namespaces.join(', ')}</span>
            </>}
            {meta.k8s_version && <>
              <span className="text-zinc-500">K8s Version</span>
              <span className="text-zinc-300 font-mono">{meta.k8s_version}</span>
            </>}
          </div>
        </div>
      )}

      {/* Findings */}
      {summary.findings_summary.length > 0 && (
        <div className="mb-4">
          <div className="text-zinc-500 text-[9px] uppercase tracking-widest mb-2">Findings</div>
          <div className="space-y-1">
            {summary.findings_summary.map((f, i) => (
              <div key={i} className="flex items-start gap-2 py-1 border-b border-zinc-800/50 last:border-0">
                <span className={`text-[8px] mt-1 ${
                  f.severity === 'critical' ? 'text-red-500' :
                  f.severity === 'warning' ? 'text-amber-500' : 'text-blue-400'
                }`}>●</span>
                <span className="text-zinc-300 text-xs">{f.title}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2 mt-auto pt-4">
        <button
          onClick={() => onOpenReport(detail)}
          className="flex-1 px-3 py-2 bg-teal-600 text-white rounded-lg text-sm font-medium transition-all duration-200 hover:bg-teal-500 hover:shadow-lg hover:shadow-teal-500/10 text-center"
        >
          Open Full Report
        </button>
        <button
          onClick={handleDelete}
          className="px-3 py-2 bg-zinc-800 text-zinc-500 border border-zinc-700 rounded-lg text-sm hover:text-zinc-300 transition-colors"
        >
          🗑
        </button>
      </div>

      {/* LLM Observability (collapsible) */}
      {summary.llm_meta && (
        <div className="mt-4 pt-3 border-t border-zinc-800">
          <button
            onClick={() => setShowObservability(!showObservability)}
            className="text-zinc-500 text-[9px] uppercase tracking-widest hover:text-zinc-400"
          >
            {showObservability ? '▾' : '▸'} LLM Observability
          </button>
          {showObservability && (
            <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs mt-2">
              <span className="text-zinc-500">Provider</span>
              <span className="text-zinc-300">{summary.llm_meta.provider}</span>
              <span className="text-zinc-500">Model</span>
              <span className="text-zinc-300 font-mono">{summary.llm_meta.model}</span>
              <span className="text-zinc-500">Tokens</span>
              <span className="text-zinc-300">
                {summary.llm_meta.input_tokens.toLocaleString()} in / {summary.llm_meta.output_tokens.toLocaleString()} out
              </span>
              <span className="text-zinc-500">Latency</span>
              <span className="text-zinc-300">{(summary.llm_meta.latency_ms / 1000).toFixed(1)}s</span>
              {summary.eval_score != null && <>
                <span className="text-zinc-500">Eval Score</span>
                <span className="text-zinc-300">{(summary.eval_score * 100).toFixed(0)}%</span>
              </>}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
