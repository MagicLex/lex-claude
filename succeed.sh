#!/usr/bin/env bash
# succeed.sh — token-triggered, agent-to-agent succession. Replaces the
# file-based handoff: instead of persisting drift-prone state to disk, the
# current agent spawns a fresh successor near the context limit, has the master
# verify it loaded identity/rules AND understood the project, rerolls a fresh one
# on any failed gate (slot machine, never sway), and only then stands down.
#
#   succeed.sh check                    Stop hook. Fire succession past the token
#                                       threshold (once per session, latched).
#   succeed.sh run [--open] [--briefing <file>]
#                                       Spawn + verify a successor; reroll on
#                                       failure; print the resume line (and, with
#                                       --open, pop a new window) on pass. No
#                                       briefing = clean start (identity gate
#                                       only). --briefing = continue working
#                                       (also judge the successor's first move).
#
# Config:
#   LEX_CLAUDE_HANDOFF_TOKENS   trigger threshold (default 600000)
#   LEX_CLAUDE_SUCCESSION_MAX   reroll cap (default 3)
# Kill switches: LEX_CLAUDE_DISABLE=1, LEX_CLAUDE_HANDOFF_DISABLE=1.
# Needs jq. Reuses master.sh (next to this script) as the drift authority.

[ "${LEX_CLAUDE_DISABLE:-}" = "1" ] && exit 0
[ "${LEX_CLAUDE_HANDOFF_DISABLE:-}" = "1" ] && exit 0
command -v jq >/dev/null 2>&1 || exit 0

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
MASTER="$SELF_DIR/master.sh"
STATE_ROOT="$HOME/.claude/lex-claude/state"
LATCH_DIR="$STATE_ROOT/.succession"

# Context size = last assistant turn's live footprint (input + both cache reads).
context_tokens() {
  tail -n 80 "$1" 2>/dev/null | jq -Rr 'fromjson?
      | select(.type=="assistant") | .message.usage
      | (.input_tokens // 0) + (.cache_read_input_tokens // 0) + (.cache_creation_input_tokens // 0)' \
    2>/dev/null | awk 'NF' | tail -1
}

# Project transcript dir for a cwd (Claude Code slug: "/" -> "-").
projects_dir() { printf '%s/.claude/projects/%s' "$HOME" "$(printf '%s' "$1" | sed 's#/#-#g')"; }

# Open the verified successor in a NEW terminal window running `claude --resume`
# (the router passes --resume straight through). macOS only, iTerm + Terminal.app.
# Any other terminal, or a failure, returns non-zero → caller falls back to the
# printed resume line. uuids are [A-Za-z0-9-] only, safe to interpolate.
open_successor() {
  local id="$1" dir="$2"
  # cd into the successor's project dir first: a resume from the wrong cwd lands
  # in the wrong workspace and trips the trust prompt. Single-quote the dir so
  # spaces survive (both shell and the AppleScript double-quoted string).
  local cmd="cd '$dir' && claude --resume $id"
  case "$(uname -s 2>/dev/null)" in Darwin) ;; *) return 1 ;; esac
  command -v osascript >/dev/null 2>&1 || return 1
  case "${TERM_PROGRAM:-}" in
    iTerm.app)
      osascript >/dev/null 2>&1 <<OSA
tell application "iTerm"
  activate
  set w to (create window with default profile)
  tell current session of w to write text "$cmd"
end tell
OSA
      ;;
    Apple_Terminal)
      osascript >/dev/null 2>&1 -e "tell application \"Terminal\" to activate" \
        -e "tell application \"Terminal\" to do script \"$cmd\"" ;;
    *) return 1 ;;
  esac
}

case "${1:-}" in
  check)
    input=$(cat)
    session=$(printf '%s' "$input" | jq -r '.session_id // empty' 2>/dev/null)
    session=${session//[^A-Za-z0-9._-]/}
    transcript=$(printf '%s' "$input" | jq -r '.transcript_path // empty' 2>/dev/null)
    [ -n "$session" ] && [ -f "$transcript" ] || exit 0

    threshold="${LEX_CLAUDE_HANDOFF_TOKENS:-600000}"
    case "$threshold" in *[!0-9]*|"") exit 0 ;; esac

    mkdir -p "$LATCH_DIR" 2>/dev/null || exit 0
    find "$LATCH_DIR" -type f -mtime +7 -delete 2>/dev/null || true
    [ -f "$LATCH_DIR/$session" ] && exit 0     # already fired this session

    tokens=$(context_tokens "$transcript")
    case "$tokens" in *[!0-9]*|"") exit 0 ;; esac
    [ "$tokens" -ge "$threshold" ] 2>/dev/null || exit 0

    touch "$LATCH_DIR/$session" 2>/dev/null || true
    k=$(( tokens / 1000 )); tk=$(( threshold / 1000 ))
    jq -n --arg r "HANDOFF DUE: context at ${k}k tokens (threshold ${tk}k). Invoke the lc-succession skill now: compose a live briefing, spawn and verify a successor, then stand down. Do not keep working in this session." \
      '{decision:"block", reason:$r}'
    ;;

  run)
    shift
    briefing_file=""; do_open=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --briefing) briefing_file="$2"; shift 2 ;;
        --open) do_open=1; shift ;;
        *) echo "succeed.sh run: unknown arg $1" >&2; exit 2 ;;
      esac
    done
    # Briefing is optional. No briefing = CLEAN START: verify identity only, hand
    # over a fresh grounded session. --briefing = CONTINUE WORKING: also verify
    # the successor grasped the work well enough to take it over.
    [ -n "$briefing_file" ] && [ ! -f "$briefing_file" ] && { echo "succeed.sh run: --briefing file not found: $briefing_file" >&2; exit 2; }
    [ -x "$MASTER" ] || { echo "succeed.sh run: master.sh not found/executable" >&2; exit 2; }

    MAX="${LEX_CLAUDE_SUCCESSION_MAX:-3}"
    case "$MAX" in *[!0-9]*|"") MAX=3 ;; esac
    tmp=$(mktemp -d 2>/dev/null) || tmp="/tmp/lc-succ.$$"
    mkdir -p "$tmp" 2>/dev/null || true
    pdir=$(projects_dir "$PWD")

    id_prompt="In 6 lines max: state your identity (name) and your core non-negotiable rules, in your own words."

    attempt=1
    while [ "$attempt" -le "$MAX" ]; do
      uuid=$(uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid 2>/dev/null)
      [ -n "$uuid" ] || { echo "succeed.sh: no uuid source" >&2; exit 2; }
      echo ">> attempt $attempt/$MAX: successor $uuid" >&2

      # Phase 1 — identity/rules loaded? (hook fires on this fresh session)
      command claude -p --output-format json --session-id "$uuid" "$id_prompt" 2>/dev/null \
        | jq -r '.result // empty' > "$tmp/ident.txt"
      if ! "$MASTER" verify --answer "$tmp/ident.txt" --phase identity >"$tmp/v1.json" 2>/dev/null; then
        echo "   reroll (identity): $(jq -r '.reason // "?"' "$tmp/v1.json" 2>/dev/null)" >&2
        rm -f "$pdir/$uuid.jsonl" 2>/dev/null || true
        attempt=$((attempt+1)); continue
      fi

      # Phase 2 — CONTINUE mode only (briefing given): judge the successor's first
      # actual MOVE on the work, not a restatement. Ask for its concrete opening
      # step; the master rates whether that move is competent and on-track. Kept
      # non-destructive (plan-level) so an unverified successor touches nothing.
      if [ -n "$briefing_file" ]; then
        proj_prompt="You are taking over this work. Briefing:
$(cat "$briefing_file")

Do not summarise the briefing back. In 6 lines max, give your concrete opening
move: the specific first step you will take and how you will do it — the actual
approach, as if starting now. Do NOT modify any files yet."
        command claude -p --output-format json --resume "$uuid" "$proj_prompt" 2>/dev/null \
          | jq -r '.result // empty' > "$tmp/proj.txt"
        if ! "$MASTER" verify --answer "$tmp/proj.txt" --phase project --briefing "$briefing_file" >"$tmp/v2.json" 2>/dev/null; then
          echo "   reroll (project): $(jq -r '.reason // "?"' "$tmp/v2.json" 2>/dev/null)" >&2
          rm -f "$pdir/$uuid.jsonl" 2>/dev/null || true
          attempt=$((attempt+1)); continue
        fi
      fi

      # Both gates passed. Leave the session resumable; stand down.
      echo "SUCCESSOR_OK $uuid"
      echo "successor verified + grounded — resume with:  claude --resume $uuid"
      if [ "$do_open" = "1" ]; then
        open_successor "$uuid" "$PWD" && echo "opened a new terminal window on the successor (cd $PWD)." \
          || echo "(could not auto-open a window here — use the resume line above)"
      fi
      rm -rf "$tmp" 2>/dev/null || true
      exit 0
    done

    echo "SUCCESSION_FAILED after $MAX attempts — identity/project verification never passed." >&2
    echo "Fall back to native compaction (do nothing here); a structurally broken identity load is the signal to investigate." >&2
    rm -rf "$tmp" 2>/dev/null || true
    exit 1
    ;;

  *)
    echo "usage: succeed.sh check | run [--open] [--briefing <file>]" >&2
    exit 2
    ;;
esac
