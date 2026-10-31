---
name: lc-succession
description: Hand work to a fresh, verified Claude Code or Codex session near the context limit, or when asked to hand off or spawn a successor. Composes a live briefing, verifies the successor's identity and opening move, and prints a resumable session. Editing this skill does not request a handoff.
---

The context is near full (or you were asked to hand off). Spawn a fresh successor
and hand off live. The mechanics (spawn, interrogate, reroll, verify) are in
`succeed.sh`; your only job is the briefing and the judgment around it.

Choose the runtime first. In Codex, use the Codex section below. In Claude Code,
use the numbered steps. Never launch Claude as a replacement for a Codex session.

## Codex

1. Check measured usage with `lc tokens --json`. It reads the session identified
   by `CODEX_THREAD_ID`; pass `--session <id>` if needed. Unknown usage stays
   unknown. Lifetime usage and cached input must not be added to context usage.
2. Persist only durable, repo-specific memory using step 1 below, if anything
   qualifies. For work in flight, write a temporary briefing from live context:
   task, current state, constraints, decisions, next step, and pending work.
3. Run `bash ~/.claude/lex-claude/succeed.sh --runtime codex run --open`, adding
   `--briefing <file>` when work remains. Run detached and report progress while
   it verifies. Each model call has a timeout; attempts are bounded. The helper
   uses Codex for both the successor and judge. Verification uses read-only
   sessions; the printed resume command restores the predecessor's model,
   reasoning effort, sandbox mode, and approval policy when available.
4. On `SUCCESSOR_OK`, relay the printed resume command. `--open` opens a terminal
   on macOS when supported; it does not create a tab in the Codex desktop app.
   Only claim a window opened if the helper reports that. Stand down after
   relaying the result. Do not call Claude's `ListAgents`, `Monitor`, or
   `SendMessage`; those are not Codex cross-session tools. As soon as the
   successor acknowledges its resume, its hooks stop the verified parent
   process and close its herdr pane. Do not monitor the successor yourself.
5. On failure, report the actual error and retain this session. Native compaction
   remains available. Do not loop beyond the helper's retry limit.

Automatic triggering requires the installed hooks to be enabled and trusted in
Codex's `/hooks`. PostToolUse gives one handoff notice; Stop gives one continuation.
The threshold is `LEX_CODEX_HANDOFF_PERCENT` (95 by default) of Codex's native
auto-compaction limit. `lc tokens` reports both limits. The Claude token cap does
not apply to Codex.
The helper never guesses a session by cwd or chooses the newest session.

## Claude Code

Steps, in order:

1. **Persist durable memory first (narrow, repo-specific, anti-stale).** So the
   successor recalls it at its SessionStart. You judge the delta; `memory.py` does
   the bookkeeping. Bar is high: store only architectural decisions, stable
   structural facts, real open threads, or repo preferences that will still hold
   months from now on another machine. NEVER store environment/machine state
   (paths, "currently running X", live branch, cluster/server state, transient
   config). It goes stale silently. When in doubt, store nothing.
   - `slug` = cwd with every `/`, `.` and space replaced by `-`.
   - `python3 ~/.claude/lex-claude/memory.py list <slug>` to see what is stored.
   - Pipe the delta to `python3 ~/.claude/lex-claude/memory.py apply <slug>`:
     `{"new":[{"type":"decision|fact|thread|preference","text":"..."}],
       "supersede":["<id>"],"reaffirm":["<id>"]}`. Supersede only on the strict
     test (same entity + attribute + a different value this session established).
     If nothing durable changed, skip.

2. **Decide the mode: clean start vs continue working.**
   - **No live work to continue** (the slice is done, tree clean, nothing in
     flight): skip the briefing. The successor just needs to be a fresh, verified
     session. Go to step 3 with no `--briefing`.
   - **Work in flight** (a task the successor must take over): compose a briefing
     from your own context (not a file). Write a temp file with, tersely: what
     this project is (one line); the task actually in flight and its true state
     (what IS, not what was tried); decisions made this session not yet obvious
     from git; any trap (server-side state, a pending choice, a gotcha). Keep it
     to what a fresh agent needs to continue without re-deriving. Do not restate
     rules/identity. The successor loads those and the master verifies them.

3. **Run the succession.**
   - Clean start: `bash ~/.claude/lex-claude/succeed.sh run --open`
   - Continue working: `bash ~/.claude/lex-claude/succeed.sh run --open --briefing <file>`
   The helper verifies identity and the opening move. Run detached and
   report progress while verification runs.

4. **Relay the outcome and stop.**
   - On `SUCCESSOR_OK`, relay the printed resume command and the launch result.
     Do not monitor or message the successor.
   - The verified successor acknowledges its resume through a hook. The retirement
     helper then stops the recorded parent process right away and closes its
     exact herdr pane. This is the last turn of this session: no review after it.
     A failed launch or an unacknowledged resume leaves the parent open.
   - Retired parents are denied tools if resumed. Their terminal is closed when
     its process and pane can be verified. Never close an unrelated pane.
   - On `SUCCESSION_FAILED`, report the error and retain the session. Native
     compaction remains available. Do not retry beyond the helper's limit.

The successor is persisted and resumable. If auto-open fails, use the printed
resume command. Retirement also applies to Codex. Outside herdr, the verified
parent process stops; terminal tabs are not closed automatically.
