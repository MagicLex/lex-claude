---
name: lc-docs-init
description: Scaffold the lex-claude doc layout (PHILOSOPHY, PRINCIPLES, INVARIANTS, OPS, TODO) in $CLAUDE_PROJECT_DIR/docs/. Creates only missing files with minimal headers — never overwrites. Use when bootstrapping documentation in a new or undocumented project.
---

Create the standard doc layout in `$CLAUDE_PROJECT_DIR/docs/`. **Never overwrite** — only create files that are missing. Do not fill content beyond the header — that's the user's job, this skill only scaffolds.

If `docs/` does not exist, create it. If `CLAUDE.md` is missing at project root, do **not** create one — that's a project-defining decision the user must drive.

Files and headers (today's date in `TODO.md` only):

- `docs/PHILOSOPHY.md`
  ```
  # Philosophy

  What we're building, in one sentence.

  Why it exists. Who it's for. What it explicitly is not.
  ```

- `docs/PRINCIPLES.md`
  ```
  # Engineering Principles

  Non-negotiable rules. If a PR violates one, it does not merge.
  ```

- `docs/INVARIANTS.md`
  ```
  # Invariants

  Architectural contracts. Verify before merging any significant change. Each item: PASS/FAIL evidence, not aspiration.
  ```

- `docs/OPS.md`
  ```
  # Operations Runbook

  Production access, deploy, troubleshooting. Not architecture — what you need when things break.

  ## Access

  ## Deploy

  ## Troubleshooting
  ```

- `docs/TODO.md`
  ```
  # TODO

  Last updated: <YYYY-MM-DD today>.

  ## Shipped

  ## In progress

  ## Next
  ```

After scaffolding, list what was created vs skipped, one line each. Stop. Do not propose to fill the content — point the user at `lc-docs-cleanup` later when they want to audit it.
