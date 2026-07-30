#!/usr/bin/env bash
# SessionStart hook — loads global identity + project docs into context.
# Wire it via ~/.claude/settings.json (see README).
# Kill switch: LEX_CLAUDE_DISABLE=1 → exit early without touching context.
# Heartbeat: writes ~/.claude/lex-claude/.last-hook (epoch) on successful run, for outside observability.

[ "${LEX_CLAUDE_DISABLE:-}" = "1" ] && exit 0

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
LEX_CLAUDE_CONTEXT_MODE="${LEX_CLAUDE_CONTEXT_MODE:-full}"

# Global ~/.claude/CLAUDE.md is auto-loaded into context by Claude Code itself
# (the `claudeMd` system-reminder). Re-dumping it here only inflated the hook
# output past the truncation limit, which cut off the acknowledgement
# instruction at the bottom. Skip it; just name it so the ack can reference it.
printf '\n===== global identity =====\nGlobal ~/.claude/CLAUDE.md is already loaded in context (no need to re-read).\n'

# Session état: live git + HANDOFF pointer (written by handoff.sh on every Stop).
# Injected before the docs so a truncated bundle still carries the state.
HANDOFF_SH="$SELF_DIR/handoff.sh"
[ -f "$HANDOFF_SH" ] && bash "$HANDOFF_SH" start

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

# The old ack ("repeat 2-3 rules, list the docs") was ceremony: unverifiable,
# burned the first turn, drifted ~60% of the time. The new one is an état
# readout the user can falsify at a glance.
printf '\n---\nRules and docs above are loaded; do not recite them and do not list them back. Open with the état instead: name the active identity from the live block (flag it if it reads BROKEN / unmanaged / none), where the last session left off (HANDOFF + the live git line), and the next slice you propose, 3 lines max. If a HANDOFF exists, Read it before any file modification (a PreToolUse gate enforces this).\n'

sh -c 'date +%s > "$1"' sh "$HOME/.claude/lex-claude/.last-hook" 2>/dev/null || true
