#!/usr/bin/env bash
# SessionStart hook — loads JeanJean global identity + project docs into context.
# Wire it via ~/.claude/settings.json (see README).

if [ -f "$HOME/.claude/CLAUDE.md" ]; then
  printf '\n===== ~/.claude/CLAUDE.md (global / JeanJean) =====\n'
  cat "$HOME/.claude/CLAUDE.md"
fi

for f in CLAUDE.md docs/PHILOSOPHY.md docs/PRINCIPLES.md docs/INVARIANTS.md docs/OPS.md docs/TODO.md; do
  p="${CLAUDE_PROJECT_DIR:-$PWD}/$f"
  if [ -f "$p" ]; then
    printf '\n===== %s =====\n' "$f"
    cat "$p"
  fi
done

printf '\n---\nThe rules above are loaded in context (JeanJean global + project CLAUDE.md + docs). Acknowledge them to the user concisely — do not say you will read them, you already have.\n'
