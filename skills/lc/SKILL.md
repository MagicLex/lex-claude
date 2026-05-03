---
name: lc
description: Surface the current lex-claude state — active identity, installed skills, install health, available CLI subcommands. Use when the user types /lc or asks what's loaded globally.
---

Run these and report concisely:

- `lc identity` — list identities, mark active.
- `lc doctor` — install health (CLAUDE.md symlink, hook, skills, CLI on PATH).
- `ls -1 ~/.claude/skills/` — globally installed skills.

Then echo the CLI surface in one line:

```
lc install | update | identity [<name>] | identity new --name <n> --desc "<d>" [--empty] | rules sync | doctor
```

If `lc` is missing from PATH, suggest: `~/.claude/lex-claude/bin/lex-claude install`.
