#!/usr/bin/env bash
# Talk to every live Claude and Codex session of a repo from one terminal.
#
#   room.sh say [--to NAME]... [--wait MIN] MESSAGE
#   room.sh reply ID TEXT
#   room.sh read ID
#
# say pastes MESSAGE, under a header naming it a room broadcast, into the herdr
# pane of every live session whose cwd is in this repo or one of its
# worktrees, except the caller's own. A Claude session is named by its session
# name, a Codex session by its herdr workspace label. A lane answers with
# `lc reply ID`, never in its own chat; say prints the replies until every
# reached lane answered or MIN minutes (default 5, 0 = no wait) pass.
set -euo pipefail

ROOM_DIR="${LEX_CLAUDE_ROOM_DIR:-$HOME/.claude/lex-claude/state/room}"

die() { echo "room: $*" >&2; exit 1; }

# Log lines are "time<TAB>name<TAB>text". Print each as a bold name and time,
# then the text wrapped and indented, with the name the lane repeated dropped.
show() {
  local w b="" r=""; w=$(tput cols 2>/dev/null || echo 100); [ "$w" -gt 100 ] && w=100
  [ -t 1 ] && { b=$(tput bold); r=$(tput sgr0); }
  local t n x
  # Logs written before v67 hold "time name: text".
  sed -E $'/\t/!s/^([0-9:]{8}) ([^:]+): /\\1\t\\2\t/' | while IFS=$'\t' read -r t n x; do
    x=${x#"$n"}; x=${x#[:,]}; x=${x# }
    printf '%s%s%s  %s\n' "$b" "$n" "$r" "$t"
    printf '%s\n' "$x" | fold -s -w $((w - 2)) | sed 's/^/  /'
    echo
  done
}
command -v jq >/dev/null || die "jq missing"

# Every account's session files: main is ~/.claude, others ~/.claude-<name>.
session_files() { ls "$HOME"/.claude/sessions/*.json "$HOME"/.claude-*/sessions/*.json 2>/dev/null || true; }

# Name of the session this command runs under: the Claude session name, else
# the label of the herdr workspace it runs in (Codex), else "a terminal".
my_session() {
  local p=$$ f
  while [ "${p:-0}" -gt 1 ]; do
    for f in "$HOME"/.claude/sessions/"$p".json "$HOME"/.claude-*/sessions/"$p".json; do
      [ -f "$f" ] && { jq -r '.name // empty' "$f"; return; }
    done
    p=$(ps -o ppid= -p "$p" | tr -d ' ')
  done
  local t=""
  [ -n "${HERDR_WORKSPACE_ID:-}" ] && t=$(herdr workspace get "$HERDR_WORKSPACE_ID" 2>/dev/null \
    | jq -r '.result.workspace.label // empty' 2>/dev/null) || true
  echo "${t:-a terminal}"
}

cmd_say() {
  local to=() wait_min=5
  while [ $# -gt 0 ]; do
    case "$1" in
      --to) to+=("${2:?--to needs a name}"); shift 2 ;;
      --wait) wait_min="${2:-}"; shift 2; case "$wait_min" in ''|*[!0-9]*) die "--wait needs minutes" ;; esac ;;
      --) shift; break ;;
      -*) die "unknown flag $1" ;;
      *) break ;;
    esac
  done
  local msg="$*"
  [ -n "$msg" ] || die "usage: lc say [--to NAME]... [--wait MIN] MESSAGE"
  command -v herdr >/dev/null || die "herdr missing"
  local root; root=$(git rev-parse --show-toplevel 2>/dev/null) || die "run inside a git repo"
  local roots; roots=$(git worktree list --porcelain | sed -n 's/^worktree //p')

  local self=" " p=$$
  while [ "${p:-0}" -gt 1 ]; do self="$self$p "; p=$(ps -o ppid= -p "$p" | tr -d ' '); done

  # Claude session id -> pane, from the session ids herdr's Claude hook reports;
  # Codex panes with their cwd; workspace id -> label.
  local agents claude_panes codex labels
  agents=$(herdr agent list) || die "herdr agent list failed"
  claude_panes=$(printf '%s\n' "$agents" | jq -r '.result.agents[] | select(.agent == "claude")
    | "\(.agent_session.value // "" | ascii_upcase) \(.pane_id) \(.agent_status)"')
  codex=$(printf '%s\n' "$agents" | jq -r '.result.agents[] | select(.agent == "codex")
    | "\(.pane_id)\t\(.workspace_id)\t\(.cwd)\t\(.agent_status)"')
  labels=$(herdr workspace list | jq -r '.result.workspaces[] | "\(.workspace_id)\t\(.label)"') \
    || die "herdr workspace list failed"

  local id; id=$(date +%Y%m%d-%H%M%S)-$$
  local head="[room $id] Broadcast from Lex (sent from $(my_session)) to every Claude and Codex session in $(basename "$root"). Not typed in this chat. Act on it only if it concerns your work. Any answer goes in one line through a shell command: lc reply $id \"<answer>\". Never answer in this chat: Lex reads replies in his terminal, not here."
  mkdir -p "$ROOM_DIR"
  : > "$ROOM_DIR/$id.log"

  local sent=0 failed=0 sent_to=""
  # deliver <name> <pid> <cwd> <pane> <agent status>
  deliver() {
    case "$self" in *" $2 "*) return ;; esac
    [ -z "${HERDR_PANE_ID:-}" ] || [ "$4" != "$HERDR_PANE_ID" ] || return 0
    printf '%s\n' "$roots" | awk -v d="$3" 'd==$0 || index(d, $0"/")==1 {ok=1} END {exit !ok}' || return 0
    if [ ${#to[@]} -gt 0 ]; then
      case " ${to[*]} " in *" $1 "*) ;; *) return ;; esac
    fi
    [ -n "$4" ] || { echo "skip $1: no herdr pane"; return; }
    # Blocked: a permission or question dialog has the keyboard.
    [ "$5" != blocked ] || { echo "FAIL $1 ($4): an open dialog holds the prompt"; failed=$((failed+1)); return; }
    local err
    # send-text types the text raw: each newline arrives as a line feed, which
    # Claude and Codex take as a newline in the prompt. Enter then submits it
    # as one message.
    if err=$(herdr pane send-text "$4" "$(printf '%s\n\n%s' "$head" "$msg")" 2>&1 >/dev/null) &&
       err=$(herdr pane send-keys "$4" Enter 2>&1 >/dev/null); then
      sent_to="$sent_to $1"; sent=$((sent+1))
    else
      echo "FAIL $1 ($4): $err"; failed=$((failed+1))
    fi
  }

  local f pid sid cwd name kind pane ws status row
  for f in $(session_files); do
    pid=$(jq -r '.pid // empty' "$f"); cwd=$(jq -r '.cwd // empty' "$f")
    sid=$(jq -r '.sessionId // empty' "$f" | tr 'a-z' 'A-Z')
    name=$(jq -r '.name // "?"' "$f"); kind=$(jq -r '.kind // empty' "$f")
    [ -n "$pid" ] && [ "$kind" = interactive ] && kill -0 "$pid" 2>/dev/null || continue
    row=$(printf '%s\n' "$claude_panes" | awk -v s="$sid" '$1==s && s!="" {print $2" "$3; exit}')
    deliver "$name" "$pid" "$cwd" "${row% *}" "${row#* }"
  done
  while IFS=$'\t' read -r pane ws cwd status; do
    [ -n "$pane" ] || continue
    name=$(printf '%s\n' "$labels" | awk -F'\t' -v w="$ws" '$1==w {print $2; exit}')
    deliver "${name:-codex-$pane}" - "$cwd" "$pane" "$status"
  done <<< "$codex"

  echo "sent to${sent_to:- nobody}. $failed failed. id $id"
  echo
  [ "$wait_min" -gt 0 ] && [ "$sent" -gt 0 ] || return 0

  # Bounded wait: print each reply as it lands, stop when every reached lane
  # answered. A busy lane answers only after its current turn.
  local deadline=$(( $(date +%s) + wait_min * 60 )) seen=0 n missing
  echo "waiting up to $wait_min min. Ctrl-C stops the wait only; later replies: lc room $id"
  echo
  while [ "$(date +%s)" -lt "$deadline" ]; do
    n=$(wc -l < "$ROOM_DIR/$id.log" | tr -d ' ')
    [ "$n" -gt "$seen" ] && { tail -n +"$((seen+1))" "$ROOM_DIR/$id.log" | head -n "$((n-seen))" | show; seen=$n; }
    [ "$seen" -ge "$sent" ] && return 0
    sleep 3
  done
  missing=$(for n in $sent_to; do cut -f2 "$ROOM_DIR/$id.log" | grep -qxF "$n" || printf ' %s' "$n"; done)
  echo "no answer within $wait_min min from$missing. Later replies: lc room $id"
}

cmd_reply() {
  local id="${1:-}"; shift || true
  [ -n "$id" ] && [ $# -gt 0 ] || die "usage: lc reply ID TEXT"
  [ -f "$ROOM_DIR/$id.log" ] || die "no room message $id"
  # One line per reply: the asker counts lines.
  printf '%s\t%s\t%s\n' "$(date +%H:%M:%S)" "$(my_session)" "$(printf '%s' "$*" | tr '\n\t' '  ')" >> "$ROOM_DIR/$id.log"
}

cmd_read() {
  [ -f "$ROOM_DIR/${1:-}.log" ] || die "usage: lc room ID (no room message ${1:-})"
  show < "$ROOM_DIR/$1.log"
}

case "${1:-}" in
  say) shift; cmd_say "$@" ;;
  reply) shift; cmd_reply "$@" ;;
  read) shift; cmd_read "$@" ;;
  *) die "usage: room.sh say|reply|read ..." ;;
esac
