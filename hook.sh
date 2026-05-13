#!/usr/bin/env bash
# SessionStart hook — loads global identity + project docs into context.
# Wire it via ~/.claude/settings.json (see README).
# Kill switch: LEX_CLAUDE_DISABLE=1 → exit early without touching context.
# Heartbeat: writes ~/.claude/lex-claude/.last-hook (epoch) on successful run, for outside observability.

[ "${LEX_CLAUDE_DISABLE:-}" = "1" ] && exit 0

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
LEX_CLAUDE_CONTEXT_MODE="${LEX_CLAUDE_CONTEXT_MODE:-full}"

if [ -f "$HOME/.claude/CLAUDE.md" ]; then
  printf '\n===== ~/.claude/CLAUDE.md (global) =====\n'
  cat "$HOME/.claude/CLAUDE.md"
fi

project_files="CLAUDE.md"
if [ "$LEX_CLAUDE_CONTEXT_MODE" != "lite" ]; then
  project_files="$project_files docs/PHILOSOPHY.md docs/CONTEXT.md docs/PRINCIPLES.md docs/INVARIANTS.md docs/OPS.md docs/TODO.md"
fi

for f in $project_files; do
  p="${CLAUDE_PROJECT_DIR:-$PWD}/$f"
  if [ -f "$p" ]; then
    printf '\n===== %s =====\n' "$f"
    cat "$p"
  fi
done

LEX_CLAUDE_CLI="$SELF_DIR/bin/lex-claude"
[ -x "$LEX_CLAUDE_CLI" ] || LEX_CLAUDE_CLI="$HOME/.claude/lex-claude/bin/lex-claude"
if [ -x "$LEX_CLAUDE_CLI" ]; then
  printf '\n===== lex-claude commands (lc) =====\n'
  "$LEX_CLAUDE_CLI" init claude
fi

LEX_CLAUDE_LANG_FILE="$HOME/.claude/lex-claude/.lang"
if [ -f "$LEX_CLAUDE_LANG_FILE" ]; then
  lang=$(cat "$LEX_CLAUDE_LANG_FILE" 2>/dev/null | tr -d '[:space:]')
  case "$lang" in
    en) printf '\n===== language =====\nRespond in English.\n' ;;
    fr) printf '\n===== language =====\nRespond in French.\n' ;;
  esac
fi

if [ "$LEX_CLAUDE_CONTEXT_MODE" = "lite" ]; then
  printf '\n---\nThe rules above are loaded in context (global CLAUDE.md + project CLAUDE.md + lex-claude commands). Acknowledge them to the user concisely. Repeat back two or three of the most relevant rules or principles so the user can see they landed, and list the documentation files that were just loaded above so the user knows what is in context. Do not say you will read them, you already have.\n'
else
  printf '\n---\nThe rules above are loaded in context (global CLAUDE.md + project CLAUDE.md + docs + lex-claude commands). Acknowledge them to the user concisely. Repeat back two or three of the most relevant rules or principles so the user can see they landed, and list the documentation files that were just loaded above so the user knows what is in context. Do not say you will read them, you already have.\n'
fi

sh -c 'date +%s > "$1"' sh "$HOME/.claude/lex-claude/.last-hook" 2>/dev/null || true
