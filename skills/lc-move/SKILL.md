---
name: lc-move
description: Move live Claude Code sessions to another account (main, alt, alt2, alt3, ...) so they keep working after one account hits its usage limit. Use when sessions fail with "You've hit your weekly limit" or "usage limit", or the user says "move the sessions to alt", "continue on the alt account", "switch accounts", "move them back to main".
---

`lc move` does the mechanics. Run it, report, stop.

1. **Target.** `--to` names an account with quota left: `main` is `~/.claude`,
   any other name is `~/.claude-<name>`. Sources are all other accounts. Pick
   the target the user named. Otherwise the account this session runs on
   (`$CLAUDE_CONFIG_DIR`) has quota, since this session answers. Never guess
   an account whose quota is unknown: ask. If the user named sessions, pass
   their ids; otherwise every live session of every other account moves.
2. **Dry run.** `lc move --to <account> --dry-run [ID...]`. Show the list in
   one line per session. Skip lines (no cmux surface, no transcript) come with
   a manual resume command: relay it.
3. **Move.** On the user's go, or straight away when the request was explicit
   ("move them all to alt"): `lc move --to <account> [ID...]`. It stops each
   old process, which kills that session's background agents, shells and
   monitors; the kickoff prompt tells the resumed session to relaunch them.
   Say so when a session had a monitor or shell running.
4. **Report.** Moved count, and every `FAIL` line with its surface. For a
   failure, read the surface: `cmux read-screen --surface <ref> --lines 30`.
   A `moved` line only means the session resumed. Read one surface after
   ~20s: a "hit your weekly limit" line means the target is capped too.

Never run it from a session that is itself on the account being drained
without saying so: the script skips its own process, so this session stays on
the source account.
