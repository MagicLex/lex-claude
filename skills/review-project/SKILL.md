---
name: review-project
description: Read project docs (CLAUDE.md + docs/*) and produce a sharp summary of state and next actions.
---

Read these files in `$CLAUDE_PROJECT_DIR` (skip missing): `CLAUDE.md`, `docs/PHILOSOPHY.md`, `docs/PRINCIPLES.md`, `docs/INVARIANTS.md`, `docs/OPS.md`, `docs/TODO.md`.

Then produce, under 25 lines:

- **Project**: 1-line purpose.
- **Non-obvious rules**: hard constraints worth flagging.
- **State**: what's done, in progress, blocked.
- **Next**: top 3 priorities.

No paraphrasing of files. Signal only.
