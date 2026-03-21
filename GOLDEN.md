# GOLDEN.md — Non-Negotiable Requirements

> These are hard constraints extracted from the original project source materials.
> The agent must verify compliance before every commit, every architecture decision,
> and every task completion. Violating any of these is a stop-the-line event —
> revert and escalate to the user.

## Project Identity

A prototype web application that ingests Kubernetes Troubleshoot support bundles and uses AI/LLM to automatically produce actionable diagnostic analysis — built as a take-home hiring project for Replicated.

## Source Materials

- **`replicated_hiring_project_3.pdf`** — 2-page hiring challenge brief from Replicated. Contains problem context, core requirements, technical constraints (deliberately open), suggested approach, expected deliverables, and evaluation signals.
- **User decisions** — App type (web app), runnability requirements, scope fences, and data handling posture captured during requirements hardening session.

## Hard Constraints

### Data & Security

- **GR-6**: Bundle data must be treated as sensitive. No bundle content may be sent to external services other than the configured LLM provider. No API keys, secrets, or credentials may be committed to the repository — use `.env.example` with placeholder values instead.
  - *Source: User decision + domain inference (bundles contain real cluster state, logs, and potentially sensitive configuration).*
  - **GR-6a (Addendum)**: Analysis results, generated reports, extracted bundle metadata (filenames, cluster IDs, namespace names, finding summaries), and LLM observability data MAY be persisted to local storage (JSON files) for session history and the session explorer feature. Raw bundle archives (.tar.gz) should still be cleaned up after extraction, but derived analysis data is not subject to the original session-scoped restriction.
    - *Justification: The original assignment doc specifies "Technical Constraints: None" and explicitly encourages exploring interesting additions to the problem domain ("put yourself in our shoes — what else can you do?"). Session persistence enables a session explorer — a realistic SRE workflow feature that demonstrates product thinking beyond single-use analysis. The no-external-services constraint remains intact.*

### Architecture

- **GR-4**: The system must be a web application.
  - *Source: User decision.*

- **GR-7**: The system must be runnable via a single setup command (`docker compose up` or equivalent one-liner). No pre-existing Kubernetes cluster may be required to run the analysis tool.
  - *Source: User decision. Derived from brief p2: "instructions that I can run against a support bundle." If the evaluator can't start it easily, it's a rejection.*

- **GR-12**: The system must accept arbitrary support bundles uploaded by the evaluator. The analysis pipeline must not be hardcoded to a specific bundle's structure or contents.
  - *Source: Brief p2: "instructions that I can run against a support bundle" — hardened to prevent demo-only implementations.*

### Performance

No specific performance metrics are golden. The brief explicitly states: "there aren't any specific metrics like latency or load times that we will be looking for." Performance belongs in the PRD as a quality goal, not here.

### Quality

- **GR-10**: The repository must be presentable: clean project structure, clear README with setup and usage instructions, no dead code, no junk commits, no generated boilerplate left unedited.
  - *Source: Brief p2: "We'll be looking at your repo. Make it presentable."*

- **GR-8**: All required environment variables, API keys, and external dependencies must be documented in the README with setup instructions.
  - *Source: User decision (runnability). Supports brief p2: "instructions that I can run."*

### Scope Boundaries

- **GR-11**: The agent must NOT build any of the following:
  - Kubernetes cluster provisioning, management, or setup tooling
  - Support bundle generation tooling
  - User authentication, accounts, or multi-tenancy
  - Billing, usage tracking, or metering
  - *Source: User decision. These are scope fences to prevent over-engineering on an open-ended brief.*

### Acceptance Criteria

- **GR-1**: The system must accept a Troubleshoot support bundle (.tar.gz archive) as its primary input.
  - *Source: Brief p2: "You must make a program that takes a Troubleshoot support bundle as input."*

- **GR-2**: The system must use AI/LLM to perform the analysis. Rule-based parsing, regex matching, or log grepping alone does not satisfy this requirement.
  - *Source: Brief p2: "uses AI to analyze it." Also in the project title: "Automated Technical Artifact Analysis."*

- **GR-3**: The system must produce actionable diagnostic output that identifies specific issues, root causes, or misconfigurations. Raw data dumps, uninterpreted log excerpts, or generic summaries do not qualify.
  - *Source: Brief p2: "outputs something useful" — hardened to a verifiable standard.*

- **GR-5**: The analysis must demonstrate breadth by processing multiple signal types from the bundle (e.g., pod logs, cluster-info, resource definitions, node status, metrics). Analyzing only a single file or signal type is insufficient.
  - *Source: Brief p2: "We are interested in the breadth and quality of your analysis."*

- **GR-9**: The repository must include a `MY_APPROACH_AND_THOUGHTS.md` file — maximum 500 words — describing the technical approach and thoughts on the problem domain.
  - *Source: Brief p2: explicit deliverable with word count constraint.*

### User-Defined

No additional hard constraints beyond those captured above. The brief deliberately imposes no language, framework, or LLM restrictions. The agent has full technical discretion within these guardrails.

---

*Note: The demo video (~2 minutes) is an expected deliverable per the brief but is out of scope for the coding agent — the user will produce it independently.*
