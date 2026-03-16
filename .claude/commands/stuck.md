You are stuck. Execute the Error Recovery protocol from CLAUDE.md:

1. STOP making changes immediately
2. Revert to last known good state: `git stash` or `git checkout .`
3. Run the test suite to confirm you're back to green
4. Present to the user:
   - **Task**: What you were trying to accomplish
   - **Attempts**: List each distinct approach you tried and why it failed
   - **Root Cause Hypothesis**: Your best guess at why this is hard
   - **Suggested Path Forward**: What you think should happen next (may include "I need your input on X")
5. Do NOT attempt another fix. Wait for user guidance.

If the test suite is not green after reverting, say so — that's a different problem.
