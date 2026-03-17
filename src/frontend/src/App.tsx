import { useCallback, useState } from 'react'
import { UploadPhase } from './components/UploadPhase'
import { ReportPhase } from './components/ReportPhase'
import { ChatPhase } from './components/ChatPhase'
import { FileViewer } from './components/FileViewer'
import FileExplorer from './components/FileExplorer'
import type { BundleManifest, DiagnosticReport } from './types/api'

type AppPhase = 'upload' | 'dashboard'

function App() {
  const [phase, setPhase] = useState<AppPhase>('upload')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [manifest, setManifest] = useState<BundleManifest | null>(null)
  const [signalSummary, setSignalSummary] = useState<Record<string, number>>({})
  const [report, setReport] = useState<DiagnosticReport | null>(null)
  const [selectedFile, setSelectedFile] = useState<{ path: string; excerpt?: string } | null>(null)

  const handleUploadComplete = useCallback(
    (sid: string, m: BundleManifest, ss: Record<string, number>) => {
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
    if (sessionId) {
      await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' }).catch(() => {})
    }
    setPhase('upload')
    setSessionId(null)
    setManifest(null)
    setSignalSummary({})
    setReport(null)
    setSelectedFile(null)
  }, [sessionId])

  // Upload phase — centered, minimal
  if (phase === 'upload') {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-zinc-950 px-4">
        <div className="mb-10 text-center">
          <h1 className="text-3xl font-bold tracking-tight text-zinc-50">Unravel</h1>
          <div className="mx-auto mt-3 mb-4 h-0.5 w-10 rounded-full bg-teal-500" />
          <p className="mt-1 text-sm text-zinc-500">
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
      {/* Sidebar */}
      <aside className="flex w-72 flex-shrink-0 flex-col border-r border-zinc-800 bg-zinc-900">
        {/* Sidebar header */}
        <div className="border-b border-zinc-800 px-4 py-4">
          <h1 className="text-sm font-bold tracking-tight text-zinc-200">Unravel</h1>
          <p className="mt-0.5 text-xs text-zinc-500">K8s Bundle Analyzer</p>
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
        <div className="border-t border-zinc-800 p-3">
          <button
            onClick={handleReset}
            className="w-full rounded-lg border border-zinc-700 px-3 py-2 text-xs text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-300"
          >
            New Analysis
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
            />
          )}

          {/* Chat — appears after report is ready */}
          {report && sessionId && <ChatPhase sessionId={sessionId} report={report} />}
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
