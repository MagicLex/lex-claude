#!/usr/bin/env bash
# Talk to every live Claude and Codex session of a repo from one terminal.
#
#   room.sh say [--to NAME]... [--wait MIN] MESSAGE
#   room.sh reply ID TEXT
#   room.sh read ID
#
# say pastes MESSAGE, under a header naming it a room broadcast, into the cmux
# surface of every live session whose cwd is in this repo or one of its
# worktrees, except the caller's own. A Claude session is named by its session
# name, a Codex session by its cmux workspace title. A lane answers with
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
# the title of the cmux workspace it runs in (Codex), else "a terminal".
my_session() {
  local p=$$ f
  while [ "${p:-0}" -gt 1 ]; do
    for f in "$HOME"/.claude/sessions/"$p".json "$HOME"/.claude-*/sessions/"$p".json; do
      [ -f "$f" ] && { jq -r '.name // empty' "$f"; return; }
    done
    p=$(ps -o ppid= -p "$p" | tr -d ' ')
  done
  local t; t=$(cmux --json tree --all 2>/dev/null | jq -r '.caller.workspace_ref as $w
    | .windows[].workspaces[] | select(.ref == $w) | .title' 2>/dev/null) || true
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
  command -v cmux >/dev/null || die "cmux missing"
  local root; root=$(git rev-parse --show-toplevel 2>/dev/null) || die "run inside a git repo"
  local roots; roots=$(git worktree list --porcelain | sed -n 's/^worktree //p')

  local self=" " p=$$
  while [ "${p:-0}" -gt 1 ]; do self="$self$p "; p=$(ps -o ppid= -p "$p" | tr -d ' '); done

  # pid -> surface ref, Codex pids with their surface, and surface ref -> workspace title.
  local procs surfaces codex titles top
  # JSON, not --format tsv: cmux 0.65.1 TSV drops the process rows.
  top=$(cmux --json top --all --processes) || die "cmux top failed"
  procs=$(printf '%s\n' "$top" | jq -r '.. | objects
    | select((.ref? // "") | startswith("surface:")) | .ref as $s
    | .processes[]? | .. | objects | select(.kind? == "process") | "\(.pid)\t\($s)\t\(.name)"')
  [ -n "$procs" ] || die "cmux top listed no processes, nothing to map sessions to"
  surfaces=$(printf '%s\n' "$procs" | awk -F'\t' '{print $1" "$2}')
  codex=$(printf '%s\n' "$procs" | awk -F'\t' '$3=="codex" {print $1" "$2}' | sort -u)
  titles=$(cmux --json tree --all | jq -r '.windows[].workspaces[] | .title as $t
    | .. | objects | select((.ref? // "") | startswith("surface:")) | "\(.ref)\t\($t)"')

  local id; id=$(date +%Y%m%d-%H%M%S)-$$
  local head="[room $id] Broadcast from Lex (sent from $(my_session)) to every Claude and Codex session in $(basename "$root"). Not typed in this chat. Act on it only if it concerns your work. Any answer goes in one line through a shell command: lc reply $id \"<answer>\". Never answer in this chat: Lex reads replies in his terminal, not here."
  mkdir -p "$ROOM_DIR"
  : > "$ROOM_DIR/$id.log"

  local sent=0 failed=0 sent_to=""
  # deliver <name> <pid> <cwd> <surface>
  deliver() {
    case "$self" in *" $2 "*) return ;; esac
    printf '%s\n' "$roots" | awk -v d="$3" 'd==$0 || index(d, $0"/")==1 {ok=1} END {exit !ok}' || return 0
    if [ ${#to[@]} -gt 0 ]; then
      case " ${to[*]} " in *" $1 "*) ;; *) return ;; esac
    fi
    [ -n "$4" ] || { echo "skip $1: no cmux surface"; return; }
    local err
    if err=$(printf '%s\n\n%s' "$head" "$msg" | cmux paste --surface "$4" --submit - 2>&1 >/dev/null); then
      sent_to="$sent_to $1"; sent=$((sent+1))
    else
      echo "FAIL $1 ($4): $err"; failed=$((failed+1))
    fi
  }

  local f pid cwd name kind surface
  for f in $(session_files); do
    pid=$(jq -r '.pid // empty' "$f"); cwd=$(jq -r '.cwd // empty' "$f")
    name=$(jq -r '.name // "?"' "$f"); kind=$(jq -r '.kind // empty' "$f")
    [ -n "$pid" ] && [ "$kind" = interactive ] && kill -0 "$pid" 2>/dev/null || continue
    deliver "$name" "$pid" "$cwd" "$(printf '%s\n' "$surfaces" | awk -v p="$pid" '$1==p {print $2; exit}')"
  done
  while read -r pid surface; do
    [ -n "$pid" ] || continue
    cwd=$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')
    name=$(printf '%s\n' "$titles" | awk -F'\t' -v s="$surface" '$1==s {print $2; exit}')
    deliver "${name:-codex-$pid}" "$pid" "$cwd" "$surface"
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
