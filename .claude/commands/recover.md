Full context recovery for a new session. Execute this sequence:

1. Read CLAUDE.md — confirm operating rules are loaded
2. Read GOLDEN.md (if present) — load non-negotiable constraints
3. Read docs/ARCHITECTURE.md — understand system structure and components
4. Read docs/IMPLEMENTATION.md — find the latest Session Log checkpoint and current task status
5. Read docs/DECISIONS.md — review recent ADRs for context on decisions made
6. Run the test suite — confirm project compiles/builds and tests pass
7. Report:
   - Current phase and task
   - Test suite status (pass count, fail count)
   - Golden requirements loaded (count and categories)
   - What the last checkpoint says to do next
   - Whether you're ready to proceed or need clarification

Do NOT start working on a task. This command is orientation only.
