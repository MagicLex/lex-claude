#!/usr/bin/env bash
# PostToolUse hook (Write|Edit|MultiEdit) — deterministic enforcement of the
# writing-style rule "no em dashes in user-facing content". A rule that can be
# a grep should not be a prayer at the top of the context.
# Scope: .md/.mdx files only, minus model-facing config (CLAUDE.md, RULES.md,
# DIGEST.md, SKILL.md, MEMORY.md, and anything under .claude/, identities/,
# memory/). Chat replies never hit this hook; only file writes do.
# Exit 2 feeds stderr back to Claude (the write itself is not undone).
# Needs jq; silent no-op without. Kill switch: LEX_CLAUDE_DISABLE=1.

[ "${LEX_CLAUDE_DISABLE:-}" = "1" ] && exit 0
command -v jq >/dev/null 2>&1 || exit 0

fp=$(jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -n "$fp" ] || exit 0

case "$fp" in
  *.md|*.mdx) ;;
  *) exit 0 ;;
esac
case "$(basename "$fp")" in
  CLAUDE.md|RULES.md|DIGEST.md|SKILL.md|MEMORY.md) exit 0 ;;
esac
case "$fp" in
  */.claude/*|*/identities/*|*/memory/*) exit 0 ;;
esac
[ -f "$fp" ] || exit 0

hits=$(grep -n '—' "$fp" 2>/dev/null | head -5)
[ -n "$hits" ] || exit 0

{
  echo "lex-claude style: em dash in $fp (user-facing md). Rules: no em dashes; rewrite with periods, commas, colons, or restructure. First hits:"
  printf '%s\n' "$hits"
} >&2
exit 2
