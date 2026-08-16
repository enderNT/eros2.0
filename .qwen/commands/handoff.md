---
description: Refresh STATE.md and TASKS.md so the next session (or the next agent) can pick up cold.
---

Close out the session so someone starting cold tomorrow loses nothing.

Current tree state:

!{git status --short}

Recent history:

!{git log --oneline -8}

Uncommitted changes:

!{git diff --stat}

Do this:

1. Update `STATE.md`: the phase, what exists now, what moved from "not decided" to
   decided, and any new gotcha worth remembering. It is a **status, not a log** —
   overwrite stale lines rather than appending. Refresh the "Last updated" line with
   today's date and who wrote it.
2. Update `TASKS.md`: check off what is done with its one-line result, mark what is in
   progress `[~]` with a line saying exactly where it stopped and what the next concrete
   step is, and add any task that this session revealed is needed.
3. If something is half-finished in the working tree, say so explicitly in `STATE.md` —
   an unfinished change nobody knows about is worse than no change.
4. Do not commit. Report what you changed in the standard format.

{{args}}
