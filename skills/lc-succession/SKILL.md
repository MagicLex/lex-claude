---
name: lc-succession
description: Hand this session's work to a fresh, verified successor when the context nears its limit. The Stop hook triggers this automatically past the token threshold (default 600k); it is also invokable by hand ("hand off", "succeed this session", "spawn a successor"). Composes a live briefing, spawns a fresh Claude Code session, has the master verify it loaded identity + rules AND understood the project, rerolls a fresh one on any failure, and stands down once a successor passes.
---

The context is near full (or you were asked to hand off). Instead of relying on
native compaction or a drift-prone handoff file, spawn a fresh successor and hand
off live. The mechanics (spawn, interrogate, reroll, verify) are in
`succeed.sh`; your only job is the briefing and the judgment around it.

Steps, in order:

1. **Persist durable memory first (narrow, repo-specific, anti-stale).** So the
   successor recalls it at its SessionStart. You judge the delta; `memory.py` does
   the bookkeeping. Bar is high: store only architectural decisions, stable
   structural facts, real open threads, or repo preferences that will still hold
   months from now on another machine. NEVER store environment/machine state
   (paths, "currently running X", live branch, cluster/server state, transient
   config) — it goes stale silently. When in doubt, store nothing.
   - `slug` = cwd with every `/`, `.` and space replaced by `-`.
   - `python3 ~/.claude/lex-claude/memory.py list <slug>` to see what is stored.
   - Pipe the delta to `python3 ~/.claude/lex-claude/memory.py apply <slug>`:
     `{"new":[{"type":"decision|fact|thread|preference","text":"..."}],
       "supersede":["<id>"],"reaffirm":["<id>"]}`. Supersede only on the strict
     test (same entity + attribute + a different value this session established).
     If nothing durable changed, skip.

2. **Compose the live briefing.** From your own context right now, not a file.
   Write a temp file (e.g. under your scratchpad dir) with, tersely:
   - what this project is (one line);
   - the task actually in flight and its true state (what IS, not what was tried);
   - decisions made this session that aren't yet obvious from git;
   - any trap the successor must know (server-side state, a pending choice, a
     gotcha). Keep it to what a fresh agent needs to continue without re-deriving.
   Do not restate the rules or identity — the successor loads those itself and the
   master verifies them.

3. **Run the succession.** Call:
   `bash ~/.claude/lex-claude/succeed.sh run --briefing <your-briefing-file>`
   Progress prints on stderr (attempts, rerolls); the outcome on stdout.

4. **Relay the outcome and stand down.**
   - `SUCCESSOR_OK <id>` → tell the user, verbatim, the resume line
     (`claude --resume <id>`). Say the successor is verified and grounded, this
     session is done, and they can close it. Then stop. Do not keep working here.
   - `SUCCESSION_FAILED` → tell the user succession failed the bounded retries,
     which means identity/rules loading is likely structurally broken (worth
     investigating, not retrying blindly). Fall back to native compaction: do
     nothing further, just stop.

Note: the successor is a persisted, resumable session — closing this one does not
close it. There is no seamless terminal baton-pass; the user resumes the successor
themselves.
