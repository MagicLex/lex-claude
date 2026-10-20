#!/usr/bin/env bash
# SessionStart hook: name the cmux workspace after the session's agent name
# (the name peers use with SendMessage, e.g. "hopsable-87"), read from Claude
# Code's session registry ~/.claude/sessions/<pid>.json.
# Title rules, so hand-added suffixes like "(lead)" survive:
#   - title already holds the name (dash or space form): leave it.
#   - title starts with an older name of the same project ("hopsable 91 ..."):
#     swap that prefix for the new name, keep the rest.
#   - default title (Claude Code, ~, a path, the dir name, successor <id>): name.
#   - any other hand-written title: prefix it with the name.
# No-op outside cmux. Kill switch: LEX_CLAUDE_DISABLE=1. Needs jq.

[ "${LEX_CLAUDE_DISABLE:-}" = "1" ] && exit 0
[ -n "${CMUX_WORKSPACE_ID:-}" ] || exit 0
command -v jq >/dev/null 2>&1 || exit 0
command -v cmux >/dev/null 2>&1 || exit 0
export CMUX_QUIET=1

input=$(cat)
sid=$(printf '%s' "$input" | jq -r '.session_id // empty' 2>/dev/null | tr 'a-z' 'A-Z')
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)
[ -n "$sid" ] || exit 0

lower() { printf '%s' "$1" | tr 'A-Z' 'a-z'; }
norm() { lower "$1" | tr '-' ' '; }
is_hex2() { case "$1" in [0-9a-f][0-9a-f]) return 0 ;; esac; return 1; }

name_for() {
  local f
  for f in "$HOME"/.claude/sessions/*.json; do
    [ -f "$f" ] || continue
    jq -r --arg s "$sid" 'select((.sessionId // "" | ascii_upcase) == $s) | .name // empty' "$f" 2>/dev/null
  done | head -n 1
}

rename() {
  local name="" title new base rest i
  # The registry entry can land a moment after the hook fires: bounded poll.
  for i in 1 2 3 4 5 6 7 8 9 10; do
    name=$(name_for); [ -n "$name" ] && break; sleep 0.3
  done
  [ -n "$name" ] || return 0

  title=$(cmux workspace list --id-format both 2>/dev/null \
    | awk -v id="$CMUX_WORKSPACE_ID" '$0 ~ id { sub(/^.*[0-9A-F-]{36}  /, ""); sub(/  \[selected\]$/, ""); print; exit }')
  [ -n "$title" ] || return 0
  case " $(norm "$title") " in *" $(norm "$name") "*) return 0 ;; esac

  base=${name%-*}
  new=""
  for sep in ' ' '-'; do
    case "$(lower "$title")" in "$(lower "$base")$sep"*) ;; *) continue ;; esac
    rest=${title:$((${#base} + 1))}
    if is_hex2 "$(lower "${rest:0:2}")" && { [ ${#rest} -eq 2 ] || [ "${rest:2:1}" = " " ]; }; then
      new="$name${rest:2}"; break
    fi
  done
  if [ -z "$new" ]; then
    case "$title" in
      "Claude Code"|"~"|*/*|"successor "*|"${cwd##*/}") new="$name" ;;
      *) new="$name $title" ;;
    esac
  fi
  cmux workspace rename "$CMUX_WORKSPACE_ID" --title "$new" >/dev/null 2>&1
}

# Detached: never delay session start.
rename </dev/null >/dev/null 2>&1 &
exit 0
