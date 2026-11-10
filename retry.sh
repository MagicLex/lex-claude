#!/usr/bin/env bash
# PostToolUseFailure hook (Bash): the same command failing with the same error
# twice in one session means the loop has stopped learning. Say so to the model.
# State: one file of sha1(command + error) per session, pruned after 2 days.
# Needs jq; silent no-op without. Kill switch: LEX_CLAUDE_DISABLE=1.

[ "${LEX_CLAUDE_DISABLE:-}" = "1" ] && exit 0
command -v jq >/dev/null 2>&1 || exit 0

in=$(cat)
sid=$(printf '%s' "$in" | jq -r '.session_id // empty' 2>/dev/null)
[ -n "$sid" ] || exit 0
key=$(printf '%s' "$in" | jq -r '[.tool_input.command // "", .error // ""] | join("\u0000")' 2>/dev/null | shasum | cut -c1-40)

dir="$HOME/.claude/lex-claude/state/retry"
mkdir -p "$dir" 2>/dev/null || exit 0
find "$dir" -type f -mtime +2 -delete 2>/dev/null
f="$dir/$sid"

if grep -qx "$key" "$f" 2>/dev/null; then
  jq -n '{hookSpecificOutput: {hookEventName: "PostToolUseFailure", additionalContext:
    "lex-claude retry: this exact command already failed with this exact error in this session. Running it again will fail the same way. Stop retrying. Reread the error, name what is missing (a wrong assumption, a missing input, the wrong layer), and change the approach or report back."}}'
  exit 0
fi
echo "$key" >> "$f"
exit 0
