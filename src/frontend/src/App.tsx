import { useCallback, useState } from 'react'
import { UploadPhase } from './components/UploadPhase'
import { ReportPhase } from './components/ReportPhase'
import { ChatPhase } from './components/ChatPhase'
import { FileViewer } from './components/FileViewer'
import { LogoMark } from './components/Logo'
import FileExplorer from './components/FileExplorer'
import { SessionExplorer } from './components/SessionExplorer'
import { SessionDetail } from './components/SessionDetail'
import { ToastContainer, useToast } from './components/Toast'
import { downloadMarkdown } from './utils/exportMarkdown'
import { buildAgentContext } from './utils/exportAgentContext'
import type { BundleManifest, ChatMessage, DiagnosticReport, SessionDetail as SessionDetailType } from './types/api'

type AppPhase = 'explorer' | 'upload' | 'dashboard'

function App() {
  const [phase, setPhase] = useState<AppPhase>('explorer')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const [isViewingSaved, setIsViewingSaved] = useState(false)
  const [manifest, setManifest] = useState<BundleManifest | null>(null)
  const [signalSummary, setSignalSummary] = useState<Record<string, number>>({})
  const [report, setReport] = useState<DiagnosticReport | null>(null)
  const [selectedFile, setSelectedFile] = useState<{ path: string; excerpt?: string } | null>(null)
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [copied, setCopied] = useState(false)
  const { toasts, addToast, dismissToast } = useToast()

  const handleUploadComplete = useCallback(
    (sid: string, m: BundleManifest, ss: Record<string, number>) => {
      // Clear any stale state from a previous session
      setReport(null)
      setSelectedFile(null)
      setChatMessages([])
      setSessionId(sid)
      setManifest(m)
      setSignalSummary(ss)
      setPhase('dashboard')
    },
    [],
  )

  const handleReportComplete = useCallback((r: DiagnosticReport) => {
    setReport(r)
  }, [])

  const handleReset = useCallback(async () => {
    if (sessionId && !isViewingSaved) {
      await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' }).catch(() => {})
    }
    setPhase('explorer')
    setSessionId(null)
    setManifest(null)
    setSignalSummary({})
    setReport(null)
    setSelectedFile(null)
    setChatMessages([])
    setSelectedSessionId(null)
    setIsViewingSaved(false)
  }, [sessionId, isViewingSaved])

  const handleOpenSavedSession = useCallback((detail: SessionDetailType) => {
    setSessionId(detail.summary.id)
    setReport(detail.report)
    setChatMessages(detail.chat || [])
    setManifest({
      total_files: 0,
      total_size_bytes: detail.summary.file_size,
      files: [],
    })
    setSignalSummary({})
    setSelectedSessionId(null)
    setIsViewingSaved(true)
    setPhase('dashboard')
  }, [])

  const handleBackToExplorer = useCallback(() => {
    setReport(null)
    setSelectedFile(null)
    setChatMessages([])
    setSessionId(null)
    setManifest(null)
    setSignalSummary({})
    setSelectedSessionId(null)
    setIsViewingSaved(false)
    setPhase('explorer')
  }, [])

  const handleSessionDeleted = useCallback((_deletedId: string) => {
    setSelectedSessionId(null)
  }, [])

  // Explorer phase — session history dashboard
  if (phase === 'explorer') {
    return (
      <div className="flex h-screen">
        <ToastContainer toasts={toasts} onDismiss={dismissToast} />
        <div className="flex-1 overflow-auto">
          <SessionExplorer
            onNewAnalysis={() => setPhase('upload')}
            onSelectSession={(id) => setSelectedSessionId(id)}
          />
        </div>
        {selectedSessionId && (
          <SessionDetail
            sessionId={selectedSessionId}
            onClose={() => setSelectedSessionId(null)}
            onOpenReport={handleOpenSavedSession}
            onDelete={handleSessionDeleted}
          />
        )}
      </div>
    )
  }

  // Upload phase — centered, minimal
  if (phase === 'upload') {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-zinc-950 px-4">
        <ToastContainer toasts={toasts} onDismiss={dismissToast} />
        <div className="mb-10 flex flex-col items-center text-center">
          <LogoMark size={48} className="mb-4" />
          <h1 className="text-3xl font-bold tracking-tight text-zinc-50">unravel</h1>
          <p className="mt-2 text-sm text-zinc-500">
            AI-powered Kubernetes support bundle analysis
          </p>
        </div>
        <UploadPhase onUploadComplete={handleUploadComplete} />
      </div>
    )
  }

  // Dashboard phase — sidebar + main content
  return (
    <div className="flex h-screen bg-zinc-950">
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
      {/* Sidebar */}
      <aside className="flex w-72 flex-shrink-0 flex-col border-r border-zinc-800 bg-zinc-900">
        {/* Sidebar header */}
        <div className="flex items-center gap-2.5 border-b border-zinc-800 px-4 py-4">
          <LogoMark size={24} />
          <div>
            <h1 className="text-sm font-bold tracking-tight text-zinc-200">unravel</h1>
            <p className="text-xs text-zinc-500">K8s Bundle Analyzer</p>
          </div>
        </div>

        {/* Bundle info */}
        {manifest && (
          <div className="border-b border-zinc-800 px-4 py-3">
            <p className="text-xs text-zinc-500">
              {manifest.total_files} files &middot;{' '}
              {manifest.total_size_bytes > 1024 * 1024
                ? `${(manifest.total_size_bytes / 1024 / 1024).toFixed(1)} MB`
                : `${(manifest.total_size_bytes / 1024).toFixed(1)} KB`}
            </p>
          </div>
        )}

        {/* File explorer */}
        <div className="flex-1 overflow-y-auto py-2">
          {manifest && sessionId && (
            <FileExplorer
              manifest={manifest}
              onFileSelect={(path) => setSelectedFile({ path })}
            />
          )}
        </div>

        {/* Sidebar footer */}
        <div className="space-y-2 border-t border-zinc-800 p-3">
          {report && (
            <>
              <button
                onClick={async () => {
                  const ctx = buildAgentContext(report, chatMessages)
                  await navigator.clipboard.writeText(ctx)
                  setCopied(true)
                  setTimeout(() => setCopied(false), 2000)
                }}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-teal-600 px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-teal-500"
              >
                {copied ? (
                  'Copied to clipboard!'
                ) : (
                  <>
                    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-3.5 w-3.5">
                      <path d="M4 11V3h8v8H4z" strokeLinecap="round" strokeLinejoin="round" />
                      <path d="M2 13V6" strokeLinecap="round" />
                      <path d="M2 13h7" strokeLinecap="round" />
                    </svg>
                    Export to Agent
                  </>
                )}
              </button>
              <button
                onClick={() => downloadMarkdown(report)}
                className="w-full rounded-lg border border-zinc-700 px-3 py-2 text-xs text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-300"
              >
                Download Report
              </button>
            </>
          )}
          <button
            onClick={handleBackToExplorer}
            className="w-full rounded-lg border border-zinc-700 px-3 py-2 text-xs text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-300"
          >
            ← Back to Explorer
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl space-y-8 p-8">
          {/* Report / Analysis progress */}
          {sessionId && manifest && (
            <ReportPhase
              sessionId={sessionId}
              manifest={manifest}
              signalSummary={signalSummary}
              onReportComplete={handleReportComplete}
              onFileSelect={(path, excerpt) => setSelectedFile({ path, excerpt })}
              onToast={addToast}
            />
          )}

          {/* Chat — appears after report is ready */}
          {report && sessionId && <ChatPhase sessionId={sessionId} report={report} onToast={addToast} onMessagesChange={setChatMessages} />}
        </div>
      </main>

      {/* File viewer slide-over */}
      {selectedFile && sessionId && (
        <FileViewer
          sessionId={sessionId}
          filePath={selectedFile.path}
          highlightExcerpt={selectedFile.excerpt}
          onClose={() => setSelectedFile(null)}
        />
      )}
    </div>
  )
}

export default App
