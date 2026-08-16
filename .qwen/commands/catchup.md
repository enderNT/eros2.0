---
description: Re-orient after time away. Reports where the project stands and what is next. Changes nothing.
---

Re-orient. **This command is read-only: do not edit, create or delete anything.**

Recent history:

!{git log --oneline -12}

Working tree:

!{git status --short}

Using that plus `STATE.md`, `PROJECT.md` and `TASKS.md`, answer in at most 15 lines:

- Where the project stands in one sentence.
- What was done most recently, and whether anything is left half-finished in the tree.
- The next task to pick up, quoted from `TASKS.md`, and whether it is ready or blocked on
  a decision.
- Any contradiction you notice between what `STATE.md` claims and what the code and git
  history actually show. Say it plainly — a stale status file is the main risk of this
  workflow.

No code, no plans, no suggestions beyond the above.

{{args}}
