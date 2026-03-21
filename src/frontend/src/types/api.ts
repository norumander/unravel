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
  signal_summary: Record<string, number>
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

export interface TimelineEvent {
  timestamp: string
  title: string
  description: string
  severity: 'critical' | 'warning' | 'info'
  source: string
}

export interface DiagnosticReport {
  executive_summary: string
  findings: Finding[]
  signal_types_analyzed: string[]
  truncation_notes: string | null
  timeline?: TimelineEvent[]
  eval_scores?: Record<string, number>
}

export interface LLMMeta {
  provider: string
  model: string
  input_tokens: number
  output_tokens: number
  latency_ms: number
  used_fallback: boolean
}

export type SSEEvent =
  | { type: 'chunk'; content: string }
  | { type: 'report'; report: DiagnosticReport }
  | { type: 'llm_meta' } & LLMMeta
  | { type: 'tool_use'; name: string; file_path: string }
  | { type: 'done' }
  | { type: 'error'; message: string }
  | { type: 'warning'; message: string }
  | { type: 'progress'; stage: string; chunks?: number; reason?: string }
  | { type: 'eval_scores'; composite_score: number; passed: boolean; dimensions: Record<string, { score: number; issues: string[] }> }

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

/* ── Session Explorer types ────────────────────────── */

export interface FindingSummary {
  severity: 'critical' | 'warning' | 'info'
  title: string
}

export interface BundleMetadataSummary {
  cluster: string | null
  namespaces: string[]
  k8s_version: string | null
  node_count: number | null
}

export interface LLMMetaSummary {
  provider: string
  model: string
  input_tokens: number
  output_tokens: number
  latency_ms: number
}

export interface SessionSummary {
  id: string
  bundle_name: string
  file_size: number
  timestamp: string
  status: 'completed' | 'error'
  bundle_metadata: BundleMetadataSummary
  findings_summary: FindingSummary[]
  llm_meta: LLMMetaSummary | null
  eval_score: number | null
  notes: string
  tags: string[]
}

export interface SessionDetail {
  summary: SessionSummary
  report: DiagnosticReport | null
  chat: ChatMessage[]
}
