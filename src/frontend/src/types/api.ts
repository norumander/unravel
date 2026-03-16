export interface BundleFile {
  path: string
  size_bytes: number
  signal_type: string
}

export interface BundleManifest {
  total_files: number
  total_size_bytes: number
  files: BundleFile[]
}

export interface UploadResponse {
  session_id: string
  manifest: BundleManifest
}

export interface SourceCitation {
  file_path: string
  excerpt: string
}

export interface Finding {
  severity: 'critical' | 'warning' | 'info'
  title: string
  description: string
  root_cause: string
  remediation: string
  source_signals: string[]
  sources?: SourceCitation[]
}

export interface DiagnosticReport {
  executive_summary: string
  findings: Finding[]
  signal_types_analyzed: string[]
  truncation_notes: string | null
}

export type SSEEvent =
  | { type: 'chunk'; content: string }
  | { type: 'report'; report: DiagnosticReport }
  | { type: 'tool_use'; name: string; file_path: string }
  | { type: 'done' }
  | { type: 'error'; message: string }

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}
