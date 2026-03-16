import { useCallback, useRef, useState, type DragEvent } from 'react'
import type { BundleManifest, UploadResponse } from '../types/api'

interface UploadPhaseProps {
  onUploadComplete: (sessionId: string, manifest: BundleManifest) => void
}

const MAX_FILE_SIZE = 500 * 1024 * 1024 // 500MB

export function UploadPhase({ onUploadComplete }: UploadPhaseProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const dragCounter = useRef(0)

  const validateFile = (file: File): string | null => {
    if (file.size > MAX_FILE_SIZE) {
      return `File is too large (${(file.size / 1024 / 1024).toFixed(0)}MB). Maximum size is 500MB.`
    }
    const name = file.name.toLowerCase()
    if (!name.endsWith('.tar.gz') && !name.endsWith('.tgz')) {
      return 'Invalid file type. Please upload a .tar.gz support bundle.'
    }
    return null
  }

  const uploadFile = useCallback(
    async (file: File) => {
      const validationError = validateFile(file)
      if (validationError) {
        setError(validationError)
        return
      }

      setError(null)
      setIsUploading(true)

      const formData = new FormData()
      formData.append('file', file)

      try {
        const response = await fetch('/api/upload', {
          method: 'POST',
          body: formData,
        })

        if (!response.ok) {
          const body = await response.json().catch(() => ({ error: 'Upload failed' }))
          throw new Error(body.error || body.detail || `HTTP ${response.status}`)
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
      dragCounter.current = 0
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
        onDragEnter={(e) => {
          e.preventDefault()
          dragCounter.current++
          setIsDragging(true)
        }}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={(e) => {
          e.preventDefault()
          dragCounter.current--
          if (dragCounter.current === 0) setIsDragging(false)
        }}
        onDrop={handleDrop}
        className={`w-full max-w-lg rounded-lg border-2 border-dashed p-12 text-center transition-colors ${
          isDragging
            ? 'border-blue-500 bg-blue-50'
            : 'border-gray-300 hover:border-gray-400'
        }`}
      >
        <div className="mb-4 text-4xl" aria-hidden="true">
          <svg xmlns="http://www.w3.org/2000/svg" className="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
          </svg>
        </div>
        <p className="mb-2 text-lg font-medium text-gray-700">
          Drop a support bundle here
        </p>
        <p className="mb-4 text-sm text-gray-500">Accepts .tar.gz files up to 500MB</p>
        <input
          type="file"
          accept=".tar.gz,.tgz"
          onChange={handleFileSelect}
          className="sr-only"
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
        <div data-testid="upload-progress" className="flex w-full max-w-lg items-center justify-center gap-3">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
          <p className="text-sm text-gray-500">Uploading and extracting bundle...</p>
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
