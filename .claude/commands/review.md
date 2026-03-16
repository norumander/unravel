Self-review the current work against the Definition of Done from CLAUDE.md.

1. Read the current task's acceptance criteria from docs/IMPLEMENTATION.md
2. Run the full test suite
3. Review your uncommitted diff (or last commit if clean)
4. Check every item on this list:
   - [ ] All acceptance criteria met
   - [ ] **No golden requirements violated** (read GOLDEN.md, check each constraint against current changes)
   - [ ] Tests pass
   - [ ] No hardcoded secrets, keys, or env-specific values
   - [ ] Error handling on all failure modes
   - [ ] Input validation on all public boundaries
   - [ ] No leftover TODOs, FIXMEs, or commented-out code
   - [ ] No unused imports, dead code, or unused variables
   - [ ] Public APIs have docstrings/JSDoc
   - [ ] Logging at appropriate levels
   - [ ] Consistent with docs/ARCHITECTURE.md
   - [ ] Non-obvious decisions logged as ADRs
5. Report which items pass and which fail
6. If any fail, fix them before marking the task DONE

Be honest. Do not rubber-stamp.
