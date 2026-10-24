---
name: lc-move
description: Move live Claude Code sessions to the other account (main or alt) so they keep working after one account hits its usage limit. Use when sessions fail with "You've hit your weekly limit" or "usage limit", or the user says "move the sessions to alt", "continue on the alt account", "switch accounts", "move them back to main".
---

`lc move` does the mechanics. Run it, report, stop.

1. **Direction.** The account that hit the limit is the source. Its sessions go
   `--to alt` (main hit the limit) or `--to main` (alt hit the limit). If the
   user named sessions, pass their ids; otherwise every live session moves.
2. **Dry run.** `lc move --to <alt|main> --dry-run [ID...]`. Show the list in
   one line per session. Skip lines (no cmux surface, no transcript) come with
   a manual resume command: relay it.
3. **Move.** On the user's go, or straight away when the request was explicit
   ("move them all to alt"): `lc move --to <alt|main> [ID...]`. It stops each
   old process, which kills that session's background agents, shells and
   monitors; the kickoff prompt tells the resumed session to relaunch them.
   Say so when a session had a monitor or shell running.
4. **Report.** Moved count, and every `FAIL` line with its surface. For a
   failure, read the surface: `cmux read-screen --surface <ref> --lines 30`.

Never run it from a session that is itself on the account being drained
without saying so: the script skips its own process, so this session stays on
the source account.
