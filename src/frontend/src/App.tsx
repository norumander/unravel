import { useCallback, useState } from 'react'
import { UploadPhase } from './components/UploadPhase'
import { ReportPhase } from './components/ReportPhase'
import { ChatPhase } from './components/ChatPhase'
import type { BundleManifest, DiagnosticReport } from './types/api'

type AppPhase = 'upload' | 'analyze' | 'chat'

function App() {
  const [phase, setPhase] = useState<AppPhase>('upload')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [manifest, setManifest] = useState<BundleManifest | null>(null)
  const [report, setReport] = useState<DiagnosticReport | null>(null)

  const handleUploadComplete = useCallback((sid: string, m: BundleManifest) => {
    setSessionId(sid)
    setManifest(m)
    setPhase('analyze')
  }, [])

  const handleReportComplete = useCallback((r: DiagnosticReport) => {
    setReport(r)
    setPhase('chat')
  }, [])

  const handleReset = useCallback(async () => {
    if (sessionId) {
      await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' }).catch(() => {})
    }
    setPhase('upload')
    setSessionId(null)
    setManifest(null)
    setReport(null)
  }, [sessionId])

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-200 bg-white px-6 py-4">
        <div className="mx-auto flex max-w-4xl items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-gray-900">Unravel</h1>
            <p className="text-sm text-gray-500">Kubernetes Support Bundle Analyzer</p>
          </div>
          {phase !== 'upload' && (
            <button
              onClick={handleReset}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
            >
              New Analysis
            </button>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-4xl p-6">
        {manifest && phase !== 'upload' && (
          <div className="mb-4 rounded-md bg-white px-4 py-2 text-sm text-gray-500 shadow-sm">
            Bundle: {manifest.total_files} files ({manifest.total_size_bytes > 1024 * 1024
              ? `${(manifest.total_size_bytes / 1024 / 1024).toFixed(1)} MB`
              : `${(manifest.total_size_bytes / 1024).toFixed(1)} KB`})
          </div>
        )}

        {phase === 'upload' && <UploadPhase onUploadComplete={handleUploadComplete} />}

        {phase === 'analyze' && sessionId && (
          <ReportPhase sessionId={sessionId} onReportComplete={handleReportComplete} />
        )}

        {phase === 'chat' && sessionId && (
          <div className="space-y-6">
            {report && (
              <details className="rounded-md bg-white p-4 shadow-sm">
                <summary className="cursor-pointer text-sm font-medium text-gray-700">
                  View Diagnostic Report ({report.findings.length} findings)
                </summary>
                <div className="mt-3 space-y-2">
                  <p className="text-sm text-gray-600">{report.executive_summary}</p>
                  {report.findings.map((f, i) => (
                    <div key={i} className="rounded border border-gray-200 p-2 text-sm">
                      <span
                        className={`mr-2 rounded px-1.5 py-0.5 text-xs font-semibold uppercase ${
                          f.severity === 'critical'
                            ? 'bg-red-100 text-red-800'
                            : f.severity === 'warning'
                              ? 'bg-yellow-100 text-yellow-800'
                              : 'bg-blue-100 text-blue-800'
                        }`}
                      >
                        {f.severity}
                      </span>
                      {f.title}
                    </div>
                  ))}
                </div>
              </details>
            )}
            <ChatPhase sessionId={sessionId} />
          </div>
        )}
      </main>
    </div>
  )
}

export default App
