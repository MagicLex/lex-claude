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

printf '\n---\nLes règles ci-dessus sont chargées en contexte (JeanJean global + CLAUDE.md projet + docs). Rappelle-les à l utilisateur de manière concise, sans dire que tu vas les lire — tu les as déjà.\n'
