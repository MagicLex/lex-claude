#!/usr/bin/env bash
# handoff.sh — session state as a maintained invariant, not a closing ceremony.
# Sessions used to die without a proper close (27% of file-writing sessions never
# committed, measured over 288 transcripts) and open without grounding. Fix: the
# harness maintains the state deterministically; the model only does the judgment.
#
# One script, five entry points (wired by bin/lex-claude):
#   stop   Stop hook          regenerate HANDOFF.md from transcript + git after
#                             every assistant turn. Kill the terminal anytime:
#                             the handoff is at most one turn stale.
#   end    SessionEnd hook    final regenerate + exit stamp (reason, dirty flag).
#   gate   PreToolUse hook    (Write|Edit|MultiEdit|NotebookEdit) deny mutations
#                             until HANDOFF.md was Read this session. An injected
#                             instruction is probabilistic; a gate is not.
#   mark   PostToolUse hook   (Read) record that HANDOFF.md was read → gate opens.
#   start  called by hook.sh  inject live git état + HANDOFF pointer + Next block.
#
# State: ~/.claude/lex-claude/state/<slug>/HANDOFF.md   (slug = cwd, [/.] → -)
#        ~/.claude/lex-claude/state/.sessions/<sid>     (gate markers, pruned 7d)
# The model-written "Next" block (from /lc-handoff) survives regeneration via
# LC_NEXT markers, same pattern as the RULES sync in identities.
# Needs jq; silent no-op without.
# Kill switches: LEX_CLAUDE_DISABLE=1, LEX_CLAUDE_HANDOFF_DISABLE=1.

[ "${LEX_CLAUDE_DISABLE:-}" = "1" ] && exit 0
[ "${LEX_CLAUDE_HANDOFF_DISABLE:-}" = "1" ] && exit 0
command -v jq >/dev/null 2>&1 || exit 0

STATE_ROOT="$HOME/.claude/lex-claude/state"
MARKER_DIR="$STATE_ROOT/.sessions"

slug_of() { printf '%s' "$1" | sed -e 's#[/. ]#-#g'; }
handoff_path() { printf '%s/%s/HANDOFF.md' "$STATE_ROOT" "$(slug_of "$1")"; }

git_state() {
  local d="$1"
  git -C "$d" rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "not a git repo"; return 0; }
  local br sha dirty ahead last
  br=$(git -C "$d" branch --show-current 2>/dev/null); [ -n "$br" ] || br="(detached)"
  sha=$(git -C "$d" rev-parse --short HEAD 2>/dev/null || echo "?")
  dirty=$(git -C "$d" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
  ahead=$(git -C "$d" rev-list --count '@{u}..HEAD' 2>/dev/null || echo "?")
  last=$(git -C "$d" log -1 --format='%s (%cr)' 2>/dev/null || echo "none")
  echo "branch: $br @ $sha | dirty: $dirty | unpushed: $ahead | last commit: $last"
}

# Regenerate HANDOFF.md for $cwd from the session transcript. Pure extraction,
# no LLM: the handoff cannot claim anything the transcript does not show.
regen() {
  local cwd="$1" session="$2" transcript="$3" endnote="$4"
  [ -n "$cwd" ] && [ -f "$transcript" ] || return 0
  local dir out tmp
  dir="$STATE_ROOT/$(slug_of "$cwd")"
  mkdir -p "$dir" 2>/dev/null || return 0
  out="$dir/HANDOFF.md"; tmp="$out.tmp.$$"

  # fromjson? skips any malformed line instead of aborting the whole pass.
  local touched asks turns tail_txt commits next_block
  touched=$(jq -Rr 'fromjson? | select(.type=="assistant" and (.isSidechain != true))
      | .message.content[]? | select(.type=="tool_use")
      | select(.name=="Write" or .name=="Edit" or .name=="MultiEdit" or .name=="NotebookEdit")
      | .input.file_path // empty' "$transcript" 2>/dev/null | awk 'NF' | sort -u)
  asks=$(jq -Rr 'fromjson? | select(.type=="user" and (.isSidechain != true) and (.isMeta != true))
      | .message.content
      | if type=="string" then . else ([.[]? | select(.type=="text") | .text] | join(" ")) end
      | gsub("[\n\r]+"; " ")' "$transcript" 2>/dev/null \
    | sed -e 's/<[^>]*>//g' | awk 'NF' | grep -v '^ *Caveat:' || true)
  turns=$(printf '%s' "$asks" | grep -c . || true)
  tail_txt=$(jq -Rr 'fromjson? | select(.type=="assistant" and (.isSidechain != true))
      | [.message.content[]? | select(.type=="text") | .text] | join(" ")
      | gsub("[\n\r]+"; " ")' "$transcript" 2>/dev/null | awk 'NF' | tail -1 | cut -c1-500)
  commits=$(jq -Rr 'fromjson? | select(.type=="assistant" and (.isSidechain != true))
      | .message.content[]? | select(.type=="tool_use") | select(.name=="Bash")
      | .input.command // empty' "$transcript" 2>/dev/null \
    | grep -cE '(^|[;&|[:space:]])git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+commit\b' || true)

  # Touched files still dirty in git = the "session died mid-flight" signal.
  local dirty_touched=""
  if git -C "$cwd" rev-parse --is-inside-work-tree >/dev/null 2>&1 && [ -n "$touched" ]; then
    local dirty_files f rel
    dirty_files=$(git -C "$cwd" status --porcelain 2>/dev/null | cut -c4- | sed -e 's/^"//' -e 's/"$//')
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      rel="${f#"$cwd"/}"
      printf '%s\n' "$dirty_files" | grep -qxF "$rel" && dirty_touched="$dirty_touched$rel"$'\n'
    done <<< "$touched"
  fi

  # The model-written Next block survives the deterministic regen.
  next_block=""
  [ -f "$out" ] && next_block=$(sed -n '/<!-- LC_NEXT_BEGIN -->/,/<!-- LC_NEXT_END -->/p' "$out" | sed '1d;$d')

  {
    printf '# HANDOFF: %s\n' "$cwd"
    printf 'updated: %s | session %.8s | user turns: %s | git commits this session: %s\n' \
      "$(date '+%Y-%m-%d %H:%M %Z')" "$session" "${turns:-0}" "${commits:-0}"
    printf '%s\n' "$(git_state "$cwd")"
    [ -n "$endnote" ] && printf '%s\n' "$endnote"
    if [ -n "$dirty_touched" ]; then
      printf 'UNCOMMITTED: files touched this session, not committed:\n'
      printf '%s' "$dirty_touched" | head -10 | sed 's/^/  - /'
    fi
    if [ -n "$touched" ]; then
      printf '\n## Touched this session\n'
      printf '%s\n' "$touched" | head -20 | sed 's/^/- /'
    fi
    if [ -n "$asks" ]; then
      printf '\n## Asks (last 3 user prompts)\n'
      printf '%s\n' "$asks" | tail -3 | cut -c1-220 | sed 's/^/- /'
    fi
    if [ -n "$tail_txt" ]; then
      printf '\n## Last assistant state\n%s\n' "$tail_txt"
    fi
    printf '\n<!-- LC_NEXT_BEGIN -->\n'
    [ -n "$next_block" ] && printf '%s\n' "$next_block"
    printf '<!-- LC_NEXT_END -->\n'
  } > "$tmp" && mv "$tmp" "$out"
  rm -f "$tmp" 2>/dev/null || true
}

case "${1:-}" in
  stop|end)
    input=$(cat)
    session=$(printf '%s' "$input" | jq -r '.session_id // empty' 2>/dev/null)
    cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)
    transcript=$(printf '%s' "$input" | jq -r '.transcript_path // empty' 2>/dev/null)
    endnote=""
    if [ "$1" = "end" ]; then
      reason=$(printf '%s' "$input" | jq -r '.reason // "unknown"' 2>/dev/null)
      endnote="ended: $reason at $(date '+%Y-%m-%d %H:%M %Z')"
    fi
    regen "$cwd" "$session" "$transcript" "$endnote"
    ;;

  gate)
    input=$(cat)
    session=$(printf '%s' "$input" | jq -r '.session_id // empty' 2>/dev/null)
    session=${session//[^A-Za-z0-9._-]/}
    cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)
    [ -n "$session" ] && [ -n "$cwd" ] || exit 0
    mkdir -p "$MARKER_DIR" 2>/dev/null || exit 0
    find "$MARKER_DIR" -type f -mtime +7 -delete 2>/dev/null || true
    [ -f "$MARKER_DIR/$session" ] && exit 0
    hp=$(handoff_path "$cwd")
    # First session in a directory: nothing to read, open the gate silently.
    [ -f "$hp" ] || { touch "$MARKER_DIR/$session" 2>/dev/null; exit 0; }
    jq -n --arg hp "$hp" '{hookSpecificOutput:{hookEventName:"PreToolUse",
      permissionDecision:"deny",
      permissionDecisionReason:("lex-claude handoff gate: this session has not read its handoff yet. Read " + $hp + " (Read tool), ground yourself on where the last session left off, then retry the modification.")}}'
    ;;

  mark)
    input=$(cat)
    session=$(printf '%s' "$input" | jq -r '.session_id // empty' 2>/dev/null)
    session=${session//[^A-Za-z0-9._-]/}
    fp=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
    [ -n "$session" ] && [ -n "$fp" ] || exit 0
    case "$fp" in
      "$STATE_ROOT"/*/HANDOFF.md)
        mkdir -p "$MARKER_DIR" 2>/dev/null || exit 0
        touch "$MARKER_DIR/$session" 2>/dev/null || true
        ;;
    esac
    ;;

  start)
    d="${CLAUDE_PROJECT_DIR:-$PWD}"
    hp=$(handoff_path "$d")
    printf '\n===== état (live) =====\n%s\n' "$(git_state "$d")"
    if [ -f "$hp" ]; then
      updated=$(sed -n 's/^updated: //p' "$hp" | head -1)
      printf 'HANDOFF: %s\n  (updated %s)\n' "$hp" "${updated:-?}"
      grep '^UNCOMMITTED' "$hp" 2>/dev/null || true
      next=$(sed -n '/<!-- LC_NEXT_BEGIN -->/,/<!-- LC_NEXT_END -->/p' "$hp" | sed '1d;$d' | awk 'NF' | head -5)
      [ -n "$next" ] && printf 'Next (from last close):\n%s\n' "$next"
      printf 'Read the HANDOFF (Read tool) before any file modification (a PreToolUse gate enforces this).\n'
    else
      printf 'HANDOFF: none yet (first tracked session in this directory).\n'
    fi
    ;;

  *)
    echo "usage: handoff.sh stop|end|gate|mark|start" >&2
    exit 1
    ;;
esac
