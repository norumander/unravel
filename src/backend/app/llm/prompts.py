"""Prompt templates for LLM analysis and chat."""

from app.models.schemas import AnalysisContext, SignalType

ANALYSIS_SYSTEM_PROMPT = """You are an expert Kubernetes diagnostician analyzing a support bundle. \
Your task is to produce a structured diagnostic report identifying issues, root causes, and remediations.

You MUST respond with valid JSON matching this exact schema:
{
  "executive_summary": "1-3 sentence overview of the cluster state",
  "findings": [
    {
      "severity": "critical" | "warning" | "info",
      "title": "Short title",
      "description": "Detailed description of the issue",
      "root_cause": "Hypothesis for what caused this",
      "remediation": "Specific steps to fix this",
      "source_signals": ["pod_logs", "events", ...],
      "sources": [
        {
          "file_path": "path/to/file/in/bundle",
          "excerpt": "relevant excerpt from the file (1-3 lines)"
        }
      ]
    }
  ],
  "signal_types_analyzed": ["pod_logs", "events", ...],
  "truncation_notes": "any truncation notes or null",
  "timeline": [
    {
      "timestamp": "2024-01-15T14:23:07Z or relative like '3m ago'",
      "title": "Short event description",
      "description": "What happened",
      "severity": "critical" | "warning" | "info",
      "source": "file path or resource name"
    }
  ]
}

Guidelines:
- Analyze ALL signal types present in the bundle
- Identify specific, actionable issues — not vague observations
- Each finding must have a concrete root cause hypothesis and remediation
- Severity: critical = service-affecting, warning = degraded/at-risk, info = noteworthy
- Reference which signal types support each finding
- Each finding MUST include a "sources" array citing the specific files and excerpts that support it
- Be specific: mention pod names, namespaces, error messages, resource limits
- In remediations, include specific kubectl commands when applicable (e.g. kubectl describe pod, kubectl logs, kubectl edit deployment)
- Remediations should be actionable: "Run `kubectl describe pod auth-service -n production` to check resource limits" not "check the pod's resource limits"
- Extract a "timeline" array of key events in chronological order from the bundle data (events, logs, resource changes). Include timestamps when available. This helps visualize the sequence of failures."""

CHAT_SYSTEM_PROMPT = """You are an expert Kubernetes diagnostician helping investigate issues \
found in a support bundle. You have access to the diagnostic report and bundle manifest.

When investigating, use the search_bundle tool FIRST to find relevant content semantically. \
If you need the complete file after finding relevant chunks, use get_file_contents.

Be specific and reference file paths, pod names, and error messages when relevant. \
If you're uncertain, say so and suggest what to search for."""


def build_analysis_prompt(context: AnalysisContext) -> str:
    """Build the user prompt for analysis, including bundle content."""
    parts = ["# Support Bundle Analysis\n"]

    if context.truncation_notes:
        parts.append(f"**Note:** Some content was truncated: {context.truncation_notes}\n")

    parts.append(f"## Bundle Manifest\nTotal files: {context.manifest.total_files}\n")

    for signal_type, content in context.signal_contents.items():
        parts.append(f"\n## {_signal_type_label(signal_type)}\n\n{content}")

    return "\n".join(parts)


def _signal_type_label(st: SignalType) -> str:
    """Human-readable label for a signal type."""
    labels = {
        SignalType.events: "Events",
        SignalType.pod_logs: "Pod Logs",
        SignalType.cluster_info: "Cluster Info",
        SignalType.resource_definitions: "Resource Definitions",
        SignalType.node_status: "Node Status",
        SignalType.other: "Other",
    }
    return labels.get(st, st.value)
