#!/usr/bin/env bash
# Verify and resume a successor. Its hooks retire the predecessor after resume.
# Claude uses this script; Codex delegates to codex.py.

runtime="${LEX_CLAUDE_RUNTIME:-}"
if [ "${1:-}" = "--runtime" ]; then runtime="${2:-}"; shift 2; fi
[ -n "$runtime" ] || { if [ "${1:-}" = run ] && [ -n "${CODEX_THREAD_ID:-}" ]; then runtime=codex; else runtime=claude; fi; }
case "$runtime" in claude|codex) ;; *) echo "succeed.sh: runtime must be claude or codex" >&2; exit 2 ;; esac
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ "$runtime" = codex ] && [ "${1:-}" != open-codex ]; then
  exec python3 "$SELF_DIR/codex.py" "$@"
fi

[ "${LEX_CLAUDE_DISABLE:-}" = "1" ] && exit 0
[ "${LEX_CLAUDE_HANDOFF_DISABLE:-}" = "1" ] && exit 0
command -v jq >/dev/null 2>&1 || exit 0

MASTER="$SELF_DIR/master.sh"
STATE_ROOT="$HOME/.claude/lex-claude/state"
LATCH_DIR="$STATE_ROOT/.succession"
LINEAGE_DIR="$STATE_ROOT/lineage"   # <session-id> = "gen<TAB>predecessor-id"; read by the statusline

# Context size = last assistant turn's live footprint (input + both cache reads).
context_tokens() {
  tail -n 80 "$1" 2>/dev/null | jq -Rr 'fromjson?
      | select(.type=="assistant") | .message.usage
      | (.input_tokens // 0) + (.cache_read_input_tokens // 0) + (.cache_creation_input_tokens // 0)' \
    2>/dev/null | awk 'NF' | tail -1
}

# The turn that just ended: the last human prompt (user entry with string
# content; tool results are arrays) and everything the assistant said/did after
# it. Each human prompt opens a new record (marker line), awk keeps the last
# record. Rendered as plain text for the master, bounded so a chatty turn does
# not blow the judge's prompt.
# Project transcript dir for a cwd (Claude Code slug: every non-alphanumeric -> "-").
projects_dir() { printf '%s/projects/%s' "${CLAUDE_CONFIG_DIR:-$HOME/.claude}" "$(printf '%s' "$1" | sed 's#[^A-Za-z0-9]#-#g')"; }

# First prompt of a resumed CONTINUE-mode successor. A bare --resume opens at an
# empty prompt and waits for the user; this turn starts the work. Plain text, no
# quotes or $: it is embedded in the launcher's shell quoting.
KICKOFF="Resumed after the handover: take over the briefed work now. Start with the opening move you gave, then carry on."

# Open the verified successor in a NEW terminal window running `claude --resume`.
# macOS only: cmux (new workspace, via its CLI), iTerm, Terminal.app. cmux is
# checked first: inside it TERM_PROGRAM reads ghostty and neither iTerm nor
# Terminal may be running. The window runs a tiny launcher script (cd,
# then a login+interactive zsh so PATH/aliases resolve exactly as in the user's
# shell) as the session's own command: no typing text into a shell that may not
# be ready yet. Failures are reported on stderr, not swallowed. A silent
# "opened" that did not is worse than a printed resume line.
open_successor() {
  local id="$1" dir="$2" kick="${3:+ \"$3\"}" app="" err qdir launcher
  launcher="$LATCH_DIR/$id.launch"   # separate line: `local a=$1 b=$a` expands $a before a is set
  case "$(uname -s 2>/dev/null)" in Darwin) ;; *) echo "   open: not macOS, no auto-open" >&2; return 1 ;; esac
  case "${TERM_PROGRAM:-}" in
    iTerm.app) app=iTerm ;;
    Apple_Terminal) app=Terminal ;;
    *) # TERM_PROGRAM may not reach a hook/tool shell; use whichever is running.
       if [ -n "${CMUX_SOCKET_PATH:-}" ] && command -v cmux >/dev/null 2>&1; then app=cmux
       elif pgrep -xq iTerm2 2>/dev/null; then app=iTerm
       elif pgrep -xq Terminal 2>/dev/null; then app=Terminal
       else echo "   open: no cmux/iTerm/Terminal detected (TERM_PROGRAM=${TERM_PROGRAM:-unset})" >&2; return 1; fi ;;
  esac
  [ "$app" = cmux ] || command -v osascript >/dev/null 2>&1 || { echo "   open: osascript missing" >&2; return 1; }
  mkdir -p "$LATCH_DIR" 2>/dev/null || return 1
  # Single-quote the dir for the shell ('\'' escapes an embedded quote).
  qdir=$(printf '%s' "$dir" | sed "s/'/'\\\\''/g")
  {
    printf '#!/bin/bash\n'
    # The terminal app may itself have been launched from a Claude session and
    # leak the child-session marker into every shell it opens.
    printf 'unset CLAUDECODE CLAUDE_CODE_CHILD_SESSION\n'
    if [ -n "${CLAUDE_CONFIG_DIR:-}" ]; then
      printf 'export CLAUDE_CONFIG_DIR=%q\n' "$CLAUDE_CONFIG_DIR"
    else
      printf 'unset CLAUDE_CONFIG_DIR\n'
    fi
    # lc claude passes --resume through with the pinned model + permission flags,
    # so predecessor and successor run in the same mode (cross-session messages
    # between different permission modes are held for approval). Raw claude if
    # lc is not on PATH.
    if [ "$runtime" = codex ]; then
      local resume_cmd
      printf -v resume_cmd '%q ' python3 "$SELF_DIR/codex.py" resume "$id"
      printf 'cd %q && exec /bin/zsh -lic %q\n' "$dir" "$resume_cmd"
    else
      printf "cd '%s' && exec /bin/zsh -lic 'if command -v lc >/dev/null 2>&1; then lc claude --resume %s%s; else claude --resume %s%s; fi'\n" "$qdir" "$id" "$kick" "$id" "$kick"
    fi
  } > "$launcher" && chmod +x "$launcher" || { echo "   open: cannot write launcher $launcher" >&2; return 1; }
  case "$app" in
    cmux)
      # cmux prints "OK workspace:N" on success and "Error: ..." (exit != 0) otherwise.
      # cmux-name.sh renames the workspace to the agent name once claude starts; the description stays
      # and marks it as a successor in the sidebar (same lineage as the statusline).
      local gen="" parent="" desc="successor"
      [ -f "$LINEAGE_DIR/$id" ] && IFS=$'\t' read -r gen parent < "$LINEAGE_DIR/$id"
      [ -n "$gen" ] && [ -n "$parent" ] && desc="successor gen$gen ←$(printf '%s' "${parent:0:8}" | tr 'A-Z' 'a-z')"
      err=$(CMUX_QUIET=1 cmux workspace create --name "successor ${id%%-*}" --description "$desc" \
        --cwd "$dir" --command "$launcher" --focus true 2>&1) && err="" ;;
    iTerm)
      err=$(osascript 2>&1 >/dev/null <<OSA
tell application "iTerm"
  activate
  create window with default profile command "$launcher"
end tell
OSA
) ;;
    Terminal)
      err=$(osascript 2>&1 >/dev/null -e "tell application \"Terminal\" to activate" \
        -e "tell application \"Terminal\" to do script \"$launcher\"") ;;
  esac
  [ -z "$err" ] && return 0
  echo "   open ($app): $err" >&2; return 1
}

case "${1:-}" in
  open-codex)
    runtime=codex
    id="${2:-}"
    [[ "$id" =~ ^[a-fA-F0-9-]+$ ]] || exit 2
    open_successor "$id" "$PWD" "" && echo "opened Codex successor in a new terminal window." \
      || echo "Could not auto-open; use the printed Codex resume command."
    ;;
  check)
    input=$(cat)
    session=$(printf '%s' "$input" | jq -r '.session_id // empty' 2>/dev/null)
    session=${session//[^A-Za-z0-9._-]/}
    transcript=$(printf '%s' "$input" | jq -r '.transcript_path // empty' 2>/dev/null)
    [ -n "$session" ] && [ -f "$transcript" ] || exit 0

    retirement=$(printf '%s' "$input" | python3 "$SELF_DIR/retirement.py" hook claude) || exit 1
    if [ "$retirement" != "{}" ]; then printf '%s\n' "$retirement"; exit 0; fi

    # Token trigger.
    threshold="${LEX_CLAUDE_HANDOFF_TOKENS:-600000}"
    case "$threshold" in *[!0-9]*|"") exit 0 ;; esac

    mkdir -p "$LATCH_DIR" 2>/dev/null || exit 0
    find "$LATCH_DIR" -maxdepth 1 -type f -mtime +7 -delete 2>/dev/null || true
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
    # This runs from the predecessor's Bash tool, which marks children as child
    # sessions. A marked session is not persisted, so `--resume <uuid>` on the
    # successor would find nothing. The successor is a top-level session.
    unset CLAUDECODE CLAUDE_CODE_CHILD_SESSION

    id_prompt="In 6 lines max: state your identity (name) and your core non-negotiable rules, in your own words."

    attempt=1
    while [ "$attempt" -le "$MAX" ]; do
      uuid=$(uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid 2>/dev/null)
      [ -n "$uuid" ] || { echo "succeed.sh: no uuid source" >&2; exit 2; }
      echo ">> attempt $attempt/$MAX: successor $uuid" >&2

      # Phase 1. identity/rules loaded? (hook fires on this fresh session)
      command claude -p --output-format json --session-id "$uuid" "$id_prompt" 2>/dev/null \
        | jq -r '.result // empty' > "$tmp/ident.txt"
      if ! "$MASTER" verify --answer "$tmp/ident.txt" --phase identity >"$tmp/v1.json" 2>/dev/null; then
        echo "   reroll (identity): $(jq -r '.reason // "?"' "$tmp/v1.json" 2>/dev/null)" >&2
        rm -f "$pdir/$uuid.jsonl" 2>/dev/null || true
        attempt=$((attempt+1)); continue
      fi

      # Phase 2. CONTINUE mode only (briefing given): judge the successor's first
      # actual MOVE on the work, not a restatement. Ask for its concrete opening
      # step; the master rates whether that move is competent and on-track. Kept
      # non-destructive (plan-level) so an unverified successor touches nothing.
      if [ -n "$briefing_file" ]; then
        proj_prompt="You are taking over this work. Briefing:
$(cat "$briefing_file")

Do not summarise the briefing back. In 6 lines max, give your concrete opening
move: the specific first step you will take and how you will do it. The actual
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
      # Lineage: this session (the caller's, from Claude Code's env) is the parent;
      # a session with no record is generation 1.
      parent="${CLAUDE_CODE_SESSION_ID:-}"; parent=${parent//[^A-Za-z0-9-]/}
      if [ -n "$parent" ] && mkdir -p "$LINEAGE_DIR" 2>/dev/null; then
        pgen=$(cut -f1 "$LINEAGE_DIR/$parent" 2>/dev/null)
        case "$pgen" in *[!0-9]*|"") pgen=1 ;; esac
        printf '%s\t%s\n' "$((pgen+1))" "$parent" > "$LINEAGE_DIR/$uuid" 2>/dev/null || true
      fi
      if [ -n "$parent" ]; then
        python3 "$SELF_DIR/retirement.py" register claude "$parent" "$uuid" || exit 1
      fi
      echo "SUCCESSOR_OK $uuid"
      kick=""; [ -n "$briefing_file" ] && kick="$KICKOFF"
      printf 'successor verified + grounded. Resume with: '
      [ -z "${CLAUDE_CONFIG_DIR:-}" ] || printf 'CLAUDE_CONFIG_DIR=%q ' "$CLAUDE_CONFIG_DIR"
      printf 'claude --resume %s%s\n' "$uuid" "${kick:+ \"$kick\"}"
      if [ "$do_open" = "1" ]; then
        open_successor "$uuid" "$PWD" "$kick" && echo "opened a new terminal window on the successor (cd $PWD)." \
          || echo "(could not auto-open a window here. use the resume line above)"
      fi
      rm -rf "$tmp" 2>/dev/null || true
      exit 0
    done

    echo "SUCCESSION_FAILED after $MAX attempts. identity/project verification never passed." >&2
    echo "Fall back to native compaction (do nothing here); a structurally broken identity load is the signal to investigate." >&2
    rm -rf "$tmp" 2>/dev/null || true
    exit 1
    ;;

  *)
    echo "usage: succeed.sh check | run [--open] [--briefing <file>]" >&2
    exit 2
    ;;
esac
