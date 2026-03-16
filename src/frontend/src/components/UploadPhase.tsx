import { useCallback, useState, type DragEvent } from 'react'
import type { BundleManifest, UploadResponse } from '../types/api'

interface UploadPhaseProps {
  onUploadComplete: (sessionId: string, manifest: BundleManifest) => void
}

export function UploadPhase({ onUploadComplete }: UploadPhaseProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)

  const uploadFile = useCallback(
    async (file: File) => {
      setError(null)
      setIsUploading(true)
      setProgress(0)

      const formData = new FormData()
      formData.append('file', file)

      try {
        const response = await fetch('/api/upload', {
          method: 'POST',
          body: formData,
        })

        setProgress(100)

        if (!response.ok) {
          const body = await response.json().catch(() => ({ error: 'Upload failed' }))
          throw new Error(body.error || `HTTP ${response.status}`)
        }

        const data: UploadResponse = await response.json()
        onUploadComplete(data.session_id, data.manifest)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Upload failed')
      } finally {
        setIsUploading(false)
      }
    },
    [onUploadComplete],
  )

  const handleDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault()
      setIsDragging(false)
      const file = e.dataTransfer.files[0]
      if (file) uploadFile(file)
    },
    [uploadFile],
  )

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) uploadFile(file)
    },
    [uploadFile],
  )

  return (
    <div className="flex flex-col items-center gap-6">
      <div
        data-testid="drop-zone"
        onDragOver={(e) => {
          e.preventDefault()
          setIsDragging(true)
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        className={`w-full max-w-lg rounded-lg border-2 border-dashed p-12 text-center transition-colors ${
          isDragging
            ? 'border-blue-500 bg-blue-50'
            : 'border-gray-300 hover:border-gray-400'
        }`}
      >
        <div className="mb-4 text-4xl">📦</div>
        <p className="mb-2 text-lg font-medium text-gray-700">
          Drop a support bundle here
        </p>
        <p className="mb-4 text-sm text-gray-500">or click to browse</p>
        <input
          type="file"
          accept=".tar.gz,.tgz"
          onChange={handleFileSelect}
          className="hidden"
          id="file-input"
          disabled={isUploading}
        />
        <label
          htmlFor="file-input"
          className="inline-block cursor-pointer rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          Select .tar.gz file
        </label>
      </div>

      {isUploading && (
        <div data-testid="upload-progress" className="w-full max-w-lg">
          <div className="h-2 overflow-hidden rounded-full bg-gray-200">
            <div
              className="h-full rounded-full bg-blue-600 transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="mt-1 text-center text-sm text-gray-500">Uploading...</p>
        </div>
      )}

      {error && (
        <div
          data-testid="upload-error"
          className="w-full max-w-lg rounded-md bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          {error}
        </div>
      )}
    </div>
  )
}
