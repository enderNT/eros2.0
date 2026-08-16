---
description: Take the next unchecked task from TASKS.md, implement it fully, and update the backlog and STATE.md.
---

Work the backlog.

1. Read `TASKS.md`. Take the **first task that is not `[x]`**, unless the user named a
   specific task in the arguments below.
2. If that task is marked *spec pending*, or you find it underspecified: **do not invent
   the design.** Write the specific questions under the task in `TASKS.md`, tell the user
   what is missing, and stop.
3. Otherwise implement it completely: code, tests, and anything the acceptance line
   demands. Follow `QWEN.md` (discovery protocol, skills, house rules) and `PROJECT.md`
   (decisions you may not contradict).
4. Run the tests yourself. Iterate until they pass or you are genuinely blocked.
5. Load the `code-simplification` skill and apply it **only to the code you just wrote**.
6. Update `TASKS.md`: mark the task `[x]` and add one line `→ result: ...`.
7. Update `STATE.md`: the phase, what exists now, and anything that moved from "not
   decided" to decided. Keep it short — overwrite stale lines, do not append history.
8. Do not commit. Leave everything in the working tree and report in the standard format.

{{args}}
