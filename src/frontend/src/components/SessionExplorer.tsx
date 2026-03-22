import { useCallback, useEffect, useMemo, useState } from 'react'
import { LogoMark } from './Logo'
import type { SessionSummary } from '../types/api'

interface SessionExplorerProps {
  onNewAnalysis: () => void
  onSelectSession: (sessionId: string) => void
}

function formatRelativeTime(timestamp: string): string {
  const diff = Date.now() - new Date(timestamp).getTime()
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export function SessionExplorer({ onNewAnalysis, onSelectSession }: SessionExplorerProps) {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'completed' | 'error'>('all')
  const [severityFilter, setSeverityFilter] = useState<'all' | 'critical'>('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const fetchSessions = useCallback(async () => {
    try {
      setLoading(true)
      const resp = await fetch('/api/history')
      if (!resp.ok) throw new Error('Failed to load sessions')
      const data = await resp.json()
      setSessions(data)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchSessions() }, [fetchSessions])

  const filtered = useMemo(() => {
    return sessions.filter(s => {
      if (statusFilter !== 'all' && s.status !== statusFilter) return false
      if (severityFilter === 'critical' && !s.findings_summary.some(f => f.severity === 'critical')) return false
      if (search) {
        const q = search.toLowerCase()
        const matchesName = s.bundle_name.toLowerCase().includes(q)
        const matchesCluster = s.bundle_metadata?.cluster?.toLowerCase().includes(q)
        const matchesNotes = s.notes?.toLowerCase().includes(q)
        if (!matchesName && !matchesCluster && !matchesNotes) return false
      }
      return true
    })
  }, [sessions, statusFilter, severityFilter, search])

  const stats = useMemo(() => ({
    total: sessions.length,
    withCritical: sessions.filter(s => s.findings_summary.some(f => f.severity === 'critical')).length,
    completed: sessions.filter(s => s.status === 'completed').length,
    errored: sessions.filter(s => s.status === 'error').length,
  }), [sessions])

  const handleRowClick = (session: SessionSummary) => {
    setSelectedId(session.id)
    onSelectSession(session.id)
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-300">
      <div className="max-w-6xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            <LogoMark size={36} />
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-zinc-50">unravel</h1>
              <p className="text-sm text-zinc-500">AI-powered Kubernetes support bundle analysis</p>
            </div>
          </div>
          <button
            onClick={onNewAnalysis}
            className="rounded-lg bg-teal-600 px-4 py-2.5 text-sm font-medium text-white transition-all duration-200 hover:bg-teal-500 hover:shadow-lg hover:shadow-teal-500/10"
          >
            + New Analysis
          </button>
        </div>

        {/* Stats bar */}
        {sessions.length > 0 && (
          <div className="grid grid-cols-4 gap-4 mb-6 p-4 bg-zinc-900 rounded-lg border border-zinc-800">
            <div className="text-center">
              <div className="text-2xl font-bold text-zinc-100">{stats.total}</div>
              <div className="text-[10px] uppercase tracking-widest text-zinc-500">Total Sessions</div>
            </div>
            <div className="text-center border-l border-zinc-800">
              <div className="text-2xl font-bold text-red-500">{stats.withCritical}</div>
              <div className="text-[10px] uppercase tracking-widest text-zinc-500">With Critical</div>
            </div>
            <div className="text-center border-l border-zinc-800">
              <div className="text-2xl font-bold text-teal-500">{stats.completed}</div>
              <div className="text-[10px] uppercase tracking-widest text-zinc-500">Completed</div>
            </div>
            <div className="text-center border-l border-zinc-800">
              <div className="text-2xl font-bold text-red-500">{stats.errored}</div>
              <div className="text-[10px] uppercase tracking-widest text-zinc-500">Errored</div>
            </div>
          </div>
        )}

        {/* Filter bar */}
        <div className="flex gap-2 mb-4">
          <input
            type="text"
            placeholder="Search by bundle name, cluster, notes..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="flex-1 bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-300 placeholder-zinc-600 focus:outline-none focus:border-zinc-600"
          />
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value as 'all' | 'completed' | 'error')}
            className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-400"
          >
            <option value="all">All Statuses</option>
            <option value="completed">Completed</option>
            <option value="error">Errored</option>
          </select>
          <select
            value={severityFilter}
            onChange={e => setSeverityFilter(e.target.value as 'all' | 'critical')}
            className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-400"
          >
            <option value="all">All Severities</option>
            <option value="critical">Has Critical</option>
          </select>
        </div>

        {/* Table */}
        {loading ? (
          <div className="text-center py-16 text-zinc-500">Loading sessions...</div>
        ) : error ? (
          <div className="text-center py-16 text-red-400">{error}</div>
        ) : sessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24">
            <LogoMark size={48} className="mb-4" />
            <p className="text-lg font-medium text-zinc-300 mb-2">No analyses yet</p>
            <p className="text-sm text-zinc-500 mb-6">Upload a support bundle to get started</p>
            <button
              onClick={onNewAnalysis}
              className="rounded-lg bg-teal-600 px-5 py-2.5 text-sm font-medium text-white transition-all duration-200 hover:bg-teal-500 hover:shadow-lg hover:shadow-teal-500/10"
            >
              Analyze Your First Bundle
            </button>
          </div>
        ) : (
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
            {/* Table header */}
            <div className="grid grid-cols-[2.5fr_1fr_1.2fr_0.8fr_80px] gap-2 px-4 py-2 text-[10px] uppercase tracking-widest text-zinc-500 border-b border-zinc-800">
              <span>Bundle</span>
              <span>Cluster</span>
              <span>Findings</span>
              <span>Analyzed</span>
              <span>Status</span>
            </div>

            {/* Rows */}
            {filtered.map(session => {
              const critCount = session.findings_summary.filter(f => f.severity === 'critical').length
              const warnCount = session.findings_summary.filter(f => f.severity === 'warning').length
              const infoCount = session.findings_summary.filter(f => f.severity === 'info').length

              return (
                <div
                  key={session.id}
                  onClick={() => handleRowClick(session)}
                  className={`grid grid-cols-[2.5fr_1fr_1.2fr_0.8fr_80px] gap-2 px-4 py-3 border-b border-zinc-800/50 cursor-pointer hover:bg-zinc-800/30 transition-colors ${
                    selectedId === session.id ? 'bg-teal-500/5 border-l-2 border-l-teal-500' : ''
                  } ${session.status === 'error' ? 'opacity-50' : ''}`}
                >
                  <div>
                    <div className="text-zinc-100 font-mono text-sm truncate">{session.bundle_name}</div>
                    {session.notes && (
                      <div className="text-zinc-500 text-xs mt-0.5 truncate">{session.notes}</div>
                    )}
                  </div>
                  <span className="text-zinc-400 font-mono text-sm self-center">
                    {session.bundle_metadata?.cluster || '—'}
                  </span>
                  <div className="self-center text-sm">
                    {session.status === 'error' ? (
                      <span className="text-zinc-500">—</span>
                    ) : (
                      <>
                        {critCount > 0 && <span className="text-red-500">{critCount} crit</span>}
                        {critCount > 0 && (warnCount > 0 || infoCount > 0) && <span className="text-zinc-600"> · </span>}
                        {warnCount > 0 && <span className="text-amber-500">{warnCount} warn</span>}
                        {warnCount > 0 && infoCount > 0 && <span className="text-zinc-600"> · </span>}
                        {infoCount > 0 && <span className="text-blue-400">{infoCount} info</span>}
                        {critCount === 0 && warnCount === 0 && infoCount === 0 && <span className="text-zinc-500">—</span>}
                      </>
                    )}
                  </div>
                  <span className="text-zinc-400 text-sm self-center">
                    {formatRelativeTime(session.timestamp)}
                  </span>
                  <span className={`text-sm self-center ${session.status === 'completed' ? 'text-teal-500' : 'text-red-500'}`}>
                    ● {session.status === 'completed' ? 'Done' : 'Error'}
                  </span>
                </div>
              )
            })}

            {filtered.length === 0 && sessions.length > 0 && (
              <div className="text-center py-8 text-zinc-500">No sessions match your filters</div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
