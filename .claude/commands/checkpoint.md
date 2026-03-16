Write a session checkpoint to docs/IMPLEMENTATION.md under the Session Log section.

Use this format:

### Checkpoint — [current date and time]
- **Phase**: [current phase — Bootstrap Phase N or Steady-State]
- **Completed**: [what was accomplished this session, be specific]
- **State**: [current project state — what works, what's wired up, test count]
- **Next**: [exact next action to take — specific enough for a fresh session to pick up]
- **Blockers**: [anything unresolved, or "None"]
- **Open Questions**: [decisions deferred to user, or "None"]

After writing the checkpoint, tell the user: "Checkpoint written. Please exit this session (`/exit` or Ctrl+C) and start a new one. Run `/recover` to pick up where we left off with: [next action]."

Do NOT continue working after writing a checkpoint. Stop and wait for the user to restart.
