#!/usr/bin/env bash
# Talk to every live Claude session of a repo from one terminal.
#
#   room.sh say [--to NAME]... [--wait MIN] MESSAGE
#   room.sh reply ID TEXT
#   room.sh read ID
#
# say pastes MESSAGE, under a header naming it a room broadcast, into the cmux
# surface of every live session whose cwd is in this repo or one of its
# worktrees. It skips the caller's own session and every workspace titled in
# LEX_CLAUDE_ROOM_SKIP (default "Gate": only the leash types there). A lane
# answers with `lc reply ID`, never in its own chat; say prints the replies
# until every reached lane answered or MIN minutes (default 5, 0 = no wait) pass.
set -euo pipefail

ROOM_DIR="${LEX_CLAUDE_ROOM_DIR:-$HOME/.claude/lex-claude/state/room}"
SKIP="${LEX_CLAUDE_ROOM_SKIP:-Gate}"

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

# Name of the Claude session this command runs under, if any.
my_session() {
  local p=$$ f
  while [ "${p:-0}" -gt 1 ]; do
    for f in "$HOME"/.claude/sessions/"$p".json "$HOME"/.claude-*/sessions/"$p".json; do
      [ -f "$f" ] && { jq -r '.name // empty' "$f"; return; }
    done
    p=$(ps -o ppid= -p "$p" | tr -d ' ')
  done
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

  # pid -> surface ref, and surface ref -> workspace title.
  local surfaces titles
  surfaces=$(cmux top --all --processes --flat --format tsv 2>/dev/null \
    | awk -F'\t' '$4=="process" && $6 ~ /^surface:/ {print $5" "$6}')
  titles=$(cmux --json tree --all | jq -r '.windows[].workspaces[] | .title as $t
    | .. | objects | select((.ref? // "") | startswith("surface:")) | "\(.ref)\t\($t)"')

  local id; id=$(date +%Y%m%d-%H%M%S)-$$
  local from; from=$(my_session); from=${from:-a terminal}
  local head="[room $id] Broadcast from Lex (sent from $from) to every Claude session in $(basename "$root"). Not typed in this chat. Act on it only if it concerns your work. Any answer goes in one line through the Bash tool: lc reply $id \"<answer>\". Never answer in this chat: Lex reads replies in his terminal, not here."
  mkdir -p "$ROOM_DIR"
  : > "$ROOM_DIR/$id.log"

  local f pid cwd name kind surface title sent=0 failed=0 sent_to=""
  for f in $(session_files); do
    pid=$(jq -r '.pid // empty' "$f"); cwd=$(jq -r '.cwd // empty' "$f")
    name=$(jq -r '.name // "?"' "$f"); kind=$(jq -r '.kind // empty' "$f")
    [ -n "$pid" ] && [ "$kind" = interactive ] && kill -0 "$pid" 2>/dev/null || continue
    case "$self" in *" $pid "*) continue ;; esac
    printf '%s\n' "$roots" | awk -v d="$cwd" 'd==$0 || index(d, $0"/")==1 {ok=1} END {exit !ok}' || continue
    if [ ${#to[@]} -gt 0 ]; then
      case " ${to[*]} " in *" $name "*) ;; *) continue ;; esac
    fi
    surface=$(printf '%s\n' "$surfaces" | awk -v p="$pid" '$1==p {print $2; exit}')
    [ -n "$surface" ] || { echo "skip $name: no cmux surface"; continue; }
    title=$(printf '%s\n' "$titles" | awk -F'\t' -v s="$surface" '$1==s {print $2; exit}')
    case " $SKIP " in *" $title "*) echo "skip $name: workspace \"$title\""; continue ;; esac
    if err=$(printf '%s\n\n%s' "$head" "$msg" | cmux paste --surface "$surface" --submit - 2>&1 >/dev/null); then
      sent_to="$sent_to $name"; sent=$((sent+1))
    else
      echo "FAIL $name ($surface): $err"; failed=$((failed+1))
    fi
  done
  echo "sent to$sent_to. $failed failed. id $id"
  echo
  [ "$wait_min" -gt 0 ] && [ "$sent" -gt 0 ] || return 0

  # Bounded wait: print each reply as it lands, stop when all reached lanes answered.
  local deadline=$(( $(date +%s) + wait_min * 60 )) seen=0 n
  while [ "$(date +%s)" -lt "$deadline" ]; do
    n=$(wc -l < "$ROOM_DIR/$id.log" | tr -d ' ')
    [ "$n" -gt "$seen" ] && { tail -n +"$((seen+1))" "$ROOM_DIR/$id.log" | head -n "$((n-seen))" | show; seen=$n; }
    [ "$seen" -ge "$sent" ] && return 0
    sleep 3
  done
  echo "$seen of $sent answered within $wait_min min. Later replies: lc room $id"
}

cmd_reply() {
  local id="${1:-}"; shift || true
  [ -n "$id" ] && [ $# -gt 0 ] || die "usage: lc reply ID TEXT"
  [ -f "$ROOM_DIR/$id.log" ] || die "no room message $id"
  local name; name=$(my_session); name=${name:-a terminal}
  # One line per reply: the asker counts lines.
  printf '%s\t%s\t%s\n' "$(date +%H:%M:%S)" "$name" "$(printf '%s' "$*" | tr '\n\t' '  ')" >> "$ROOM_DIR/$id.log"
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
