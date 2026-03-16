# My Approach and Thoughts

## Technical Approach

I built Unravel as a two-container web application: a React SPA frontend and a FastAPI backend, orchestrated with Docker Compose. The core insight driving the architecture is that support bundle analysis is a pipeline problem — raw data flows through classification, assembly, and AI analysis stages — and the system should be transparent about each stage.

**Signal classification** is the foundation. Troubleshoot bundles follow predictable directory conventions, so path-based pattern matching reliably categorizes files into five signal types: pod logs, events, cluster info, resource definitions, and node status. This classification drives everything downstream — it determines what content reaches the LLM, in what priority order, and enables the structured report to trace findings back to specific signal types.

**Smart context truncation** solves the practical problem that real bundles often exceed LLM context windows. The priority-based strategy (events and pod logs first, then cluster info, then resource definitions, then node status) reflects operational reality: events and logs are almost always the most diagnostic signals for Kubernetes issues. The system annotates what was truncated so the AI and user both know what was excluded.

**The provider interface** abstracts LLM-specific SDK differences behind a common async streaming interface. Both Anthropic and OpenAI implementations support streaming responses and tool-use for chat file retrieval. Swapping providers is a single environment variable change.

**Chat with tool-use** is where the system becomes genuinely useful beyond the initial report. The LLM can request specific files from the bundle via `get_file_contents`, enabling targeted investigation. This mirrors how a human engineer works: scan the summary, then drill into specific files to confirm hypotheses.

## Thoughts on the Problem Domain

Support bundle analysis sits at an interesting intersection. The data is highly structured (Kubernetes resources are typed, logs follow patterns, events have schemas) but the diagnostic reasoning is highly contextual. Rule-based tools can flag known patterns, but the real value is correlating signals across sources — connecting an OOM event to a pod's memory limits to the application logs showing allocation failures.

LLMs are well-suited here because they can synthesize across heterogeneous data types without explicit programming for each correlation. The structured report format forces the AI to be specific rather than vague, and the interactive chat allows engineers to follow threads the automated analysis might not prioritize.

The key constraint — treating bundle data as sensitive and keeping everything in-memory — is the right default. Support bundles contain real cluster state, potentially including secrets, configuration, and internal infrastructure details. No-persistence-by-default is the responsible choice.

If I were extending this, I'd add: confidence scoring based on cross-signal corroboration, diff analysis between time-separated bundles to track issue progression, and a self-hosted Langfuse deployment for prompt tracing without compromising data sovereignty.
