#!/usr/bin/env bash
# Talk to every live Claude and Codex session of a repo from one terminal.
#
#   room.sh room                     full-screen view; no terminal: list rooms
#   room.sh room ID                  open room ID; no terminal: print its thread
#   room.sh room [--to NAME]... [--wait MIN] [--in ID] [--] MESSAGE
#   room.sh reply ID TEXT
#   room.sh lanes                    live sessions of this repo, one name per line
#   room.sh go NAME
#
# A broadcast pastes MESSAGE, under a header naming it a room message, into the
# cmux surface of every live session whose cwd is in this repo or one of its
# worktrees, except the caller's own. Not cmux agent message: in cmux 0.65.1 it
# stays queued for a Claude lane that cmux does not see as idle, with no error. A Claude session is named by its session
# name, a Codex session by its cmux workspace title. A lane answers with
# `lc reply ID`, never in its own chat; the sender prints the replies until
# every reached lane answered or MIN minutes (default 5, 0 = no wait) pass.
# --in ID sends a follow-up in room ID to the lanes it reached (or --to NAME).
#
# Files per room in ROOM_DIR, lines "time<TAB>name<TAB>text":
#   ID.log  lane replies only
#   ID.lex  what was sent, name "SENDER > lane, lane" (SENDER is Lex, or the lane that sent)
#   ID.to   names of the lanes the room reached, one per line
#   ID.sid  "name<TAB>session ID" of those lanes, to find them after lc move renames them
set -euo pipefail

ROOM_DIR="${LEX_CLAUDE_ROOM_DIR:-$HOME/.claude/lex-claude/state/room}"

die() { echo "room: $*" >&2; exit 1; }

# Print each line as a bold name and time, then the text wrapped and indented,
# with the name the lane repeated dropped.
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

# The thread of a room: Lex's lines and the replies, in time order.
thread() {
  local f; for f in "$ROOM_DIR/$1.lex" "$ROOM_DIR/$1.log"; do [ -f "$f" ] || : > "$f"; done
  sort -s -t $'\t' -k1,1 "$ROOM_DIR/$1.lex" "$ROOM_DIR/$1.log"
}

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

# "name<TAB>pid<TAB>cwd<TAB>surface<TAB>session ID" for every live interactive
# Claude session and every Codex process in cmux. Surface is empty outside
# cmux, the session ID for Codex.
live() {
  command -v cmux >/dev/null || die "cmux missing"
  local procs surfaces codex titles top f pid cwd name kind surface
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
  for f in $(session_files); do
    IFS=$'\t' read -r pid cwd name kind sid < <(jq -r '[.pid // "", .cwd // "", .name // "?", .kind // "", .sessionId // ""] | @tsv' "$f")
    [ -n "$pid" ] && [ "$kind" = interactive ] && kill -0 "$pid" 2>/dev/null || continue
    printf '%s\t%s\t%s\t%s\t%s\n' "$name" "$pid" "$cwd" "$(printf '%s\n' "$surfaces" | awk -v p="$pid" '$1==p {print $2; exit}')" "$sid"
  done
  while read -r pid surface; do
    [ -n "$pid" ] || continue
    cwd=$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')
    name=$(printf '%s\n' "$titles" | awk -F'\t' -v s="$surface" '$1==s {print $2; exit}')
    printf '%s\t%s\t%s\t%s\t\n' "${name:-codex-$pid}" "$pid" "$cwd" "$surface"
  done <<< "$codex"
}

# live, minus the session this command runs under.
others() {
  local self=" " p=$$ lanes
  while [ "${p:-0}" -gt 1 ]; do self="$self$p "; p=$(ps -o ppid= -p "$p" | tr -d ' '); done
  lanes=$(live) || exit 1
  printf '%s\n' "$lanes" | awk -F'\t' -v self="$self" 'NF && index(self, " "$2" ")==0'
}

# others, limited to the repo at $PWD and its worktrees.
repo_lanes() {
  local roots lanes
  roots=$(git worktree list --porcelain 2>/dev/null | sed -n 's/^worktree //p') || true
  [ -n "$roots" ] || die "run inside a git repo"
  lanes=$(others) || exit 1
  # Roots go through the environment: BSD awk rejects a newline in -v.
  printf '%s\n' "$lanes" | ROOTS="$roots" awk -F'\t' 'BEGIN {n = split(ENVIRON["ROOTS"], r, "\n")}
    NF { for (i = 1; i <= n; i++) if ($3 == r[i] || index($3, r[i] "/") == 1) { print; next } }'
}

# Who sends: the Claude or Codex lane this command runs under, else Lex.
sender() {
  local p=$$ f
  while [ "${p:-0}" -gt 1 ]; do
    for f in "$HOME"/.claude/sessions/"$p".json "$HOME"/.claude-*/sessions/"$p".json; do
      [ -f "$f" ] && { jq -r '.name // "a lane"' "$f"; return; }
    done
    [ "$(ps -o comm= -p "$p" | sed 's|.*/||')" = codex ] && { my_session; return; }
    p=$(ps -o ppid= -p "$p" | tr -d ' ')
  done
  echo Lex
}

cmd_say() {
  local to=() wait_min=5 id="" waited=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --to) to+=("${2:?--to needs a name}"); shift 2 ;;
      --wait) wait_min="${2:-}"; waited=1; shift 2; case "$wait_min" in ''|*[!0-9]*) die "--wait needs minutes" ;; esac ;;
      --in) id="${2:?--in needs a room ID}"; shift 2 ;;
      --) shift; break ;;
      -*) die "unknown flag $1" ;;
      *) break ;;
    esac
  done
  local msg="$*"
  [ -n "$msg" ] || die "usage: lc room [--to NAME]... [--wait MIN] [--in ID] [--] MESSAGE"

  local root="" head name from; from=$(sender)
  if [ -n "$id" ]; then
    # A follow-up goes by name to lanes the room reached, wherever they run now.
    [ -f "$ROOM_DIR/$id.log" ] || die "no room message $id"
    if [ ${#to[@]} -eq 0 ]; then
      [ -s "$ROOM_DIR/$id.to" ] || die "room $id has no recorded lanes, name them with --to"
      while read -r name; do to+=("$name"); done < "$ROOM_DIR/$id.to"
    fi
    head="[room $id] Follow-up from $from in room $id. Not typed in this chat. Answer in one line through a shell command: lc reply $id \"<answer>\". Never answer in this chat: replies are read with lc room, not here."
  else
    local root; root=$(git rev-parse --show-toplevel 2>/dev/null) || die "run inside a git repo"
    id=$(date +%Y%m%d-%H%M%S)-$$
    head="[room $id] Broadcast from $from to every Claude and Codex session in $(basename "$root"). Not typed in this chat. Act on it only if it concerns your work. Any answer goes in one line through a shell command: lc reply $id \"<answer>\". Never answer in this chat: replies are read with lc room, not here."
    mkdir -p "$ROOM_DIR"
    : > "$ROOM_DIR/$id.log"
  fi

  local sent=0 failed=0 sent_names="" failed_names="" sids="" pid cwd surface sid err lanes new=1 want="" t now
  [ -n "$root" ] || new=0
  if [ "$new" = 1 ]; then lanes=$(repo_lanes) || { rm -f "$ROOM_DIR/$id.log"; exit 1; }; else lanes=$(others) || exit 1; fi
  [ ${#to[@]} -eq 0 ] || want=$(printf '%s\n' "${to[@]}")
  # lc move renames a lane but keeps its session ID: a name the room recorded
  # goes to the live lane with that ID, whatever it is called now.
  if [ "$new" = 0 ] && [ -n "$want" ] && [ -f "$ROOM_DIR/$id.sid" ]; then
    want=$(printf '%s\n' "$want" | while IFS= read -r t; do
      sid=$(awk -F'\t' -v n="$t" '$1==n {print $2; exit}' "$ROOM_DIR/$id.sid")
      now=""; [ -z "$sid" ] || now=$(printf '%s\n' "$lanes" | awk -F'\t' -v s="$sid" '$5==s {print $1; exit}')
      printf '%s\n' "${now:-$t}"
    done)
  fi
  while IFS=$'\t' read -r name pid cwd surface sid; do
    [ -n "$pid" ] || continue
    [ -z "$want" ] || printf '%s\n' "$want" | grep -qxF -- "$name" || continue
    [ -n "$surface" ] || { echo "skip $name: no cmux surface"; failed_names+="$name"$'\n'; continue; }
    if err=$(printf '%s\n\n%s' "$head" "$msg" | cmux paste --surface "$surface" --submit - 2>&1 >/dev/null); then
      sent_names+="$name"$'\n'; sids+="$name"$'\t'"$sid"$'\n'; sent=$((sent+1))
    else
      echo "FAIL $name ($surface): $err"; failed=$((failed+1)); failed_names+="$name"$'\n'
    fi
  done <<< "$lanes"

  # A new room nobody got is not kept. Its log exists before delivery so an
  # early reply has a place to land.
  if [ "$new" = 1 ] && [ "$sent" -eq 0 ]; then rm -f "$ROOM_DIR/$id.log"; echo "sent to nobody. $failed failed."; return 0; fi
  # Names can hold spaces (a Codex lane is named by its workspace title), so
  # lists are one name per line in files and ", "-joined on screen.
  local joined; joined=$(printf '%s' "$sent_names" | awk 'NF {printf "%s%s", (n++ ? ", " : ""), $0}')
  if [ "$new" = 1 ]; then
    printf '%s' "$sent_names" > "$ROOM_DIR/$id.to"
    printf '%s' "$sids" > "$ROOM_DIR/$id.sid"
  elif [ -f "$ROOM_DIR/$id.sid" ]; then
    # Write renamed lanes back, so the room shows the names in use now.
    local renamed; renamed=$(while IFS=$'\t' read -r t sid; do
      now=""; [ -z "$sid" ] || now=$(printf '%s\n' "$lanes" | awk -F'\t' -v s="$sid" '$5==s {print $1; exit}')
      printf '%s\t%s\n' "${now:-$t}" "$sid"
    done < "$ROOM_DIR/$id.sid")
    printf '%s\n' "$renamed" > "$ROOM_DIR/$id.sid"
    printf '%s\n' "$renamed" | cut -f1 > "$ROOM_DIR/$id.to"
  fi
  [ "$sent" -gt 0 ] && printf '%s\t%s > %s\t%s\n' "$(date +%H:%M:%S)" "$from" "$joined" "$(printf '%s' "$msg" | tr '\n\t' '  ')" >> "$ROOM_DIR/$id.lex"
  # A named lane that is no longer live (closed, or retired by a successor) is
  # said, not dropped silently.
  local gone; gone=$(printf '%s\n' "$want" | while IFS= read -r t; do
    if [ -n "$t" ] && ! printf '%s%s' "$sent_names" "$failed_names" | grep -qxF -- "$t"; then printf '%s\n' "$t"; fi
  done | awk 'NF {printf "%s%s", (n++ ? ", " : ""), $0}')
  [ -z "$gone" ] || echo "not live: $gone"
  echo "sent to ${joined:-nobody}. $failed failed. id $id"
  echo
  [ "$wait_min" -gt 0 ] && [ "$sent" -gt 0 ] || return 0
  # In a terminal, without an explicit --wait or a failure to read above, the
  # room opens in the full-screen view.
  if [ -t 0 ] && [ -t 1 ] && [ "$waited" = 0 ] && [ "$failed" = 0 ]; then
    exec python3 "$(dirname "$0")/roomtui.py" "$ROOM_DIR" "$id"
  fi

  # Bounded wait: print each reply as it lands, stop when every reached lane
  # answered since this message. A busy lane answers only after its current turn.
  local deadline=$(( $(date +%s) + wait_min * 60 )) seen n missing
  seen=$(wc -l < "$ROOM_DIR/$id.log" | tr -d ' ')
  local start=$seen
  echo "waiting up to $wait_min min. Ctrl-C stops the wait only; later replies: lc room $id"
  echo
  answered() { tail -n +"$((start+1))" "$ROOM_DIR/$id.log" | cut -f2 | sort -u | grep -cxF -f <(printf '%s' "$sent_names") || true; }
  while [ "$(date +%s)" -lt "$deadline" ]; do
    n=$(wc -l < "$ROOM_DIR/$id.log" | tr -d ' ')
    [ "$n" -gt "$seen" ] && { tail -n +"$((seen+1))" "$ROOM_DIR/$id.log" | head -n "$((n-seen))" | show; seen=$n; }
    [ "$(answered)" -ge "$sent" ] && return 0
    sleep 3
  done
  missing=$(printf '%s' "$sent_names" | while IFS= read -r n; do
    tail -n +"$((start+1))" "$ROOM_DIR/$id.log" | cut -f2 | grep -qxF -- "$n" || printf '%s\n' "$n"
  done | awk 'NF {printf "%s%s", (n++ ? ", " : ""), $0}')
  echo "no answer within $wait_min min from $missing. Later replies: lc room $id"
}

cmd_reply() {
  local id="${1:-}"; shift || true
  [ -n "$id" ] && [ $# -gt 0 ] || die "usage: lc reply ID TEXT"
  [ -f "$ROOM_DIR/$id.log" ] || die "no room message $id"
  # One line per reply: the asker counts lines.
  printf '%s\t%s\t%s\n' "$(date +%H:%M:%S)" "$(my_session)" "$(printf '%s' "$*" | tr '\n\t' '  ')" >> "$ROOM_DIR/$id.log"
}

# Newest rooms first: "ID<TAB>replies<TAB>first message".
rooms() {
  local f id
  for f in $(ls -t "$ROOM_DIR"/*.log 2>/dev/null | head -n "${1:-15}"); do
    id=$(basename "$f" .log)
    printf '%s\t%s\t%s\n' "$id" "$(wc -l < "$f" | tr -d ' ')" \
      "$( { head -n1 "$ROOM_DIR/$id.lex" 2>/dev/null || true; } | cut -f3 | cut -c1-70)"
  done
}

# Bring the cmux tab of lane NAME to the front.
jump() {
  local name=$1 surface loc lanes
  lanes=$(live) || return
  surface=$(printf '%s\n' "$lanes" | awk -F'\t' -v n="$1" '$1==n {print $4; exit}')
  [ -n "$surface" ] || { echo "no live lane named $1 in cmux"; return; }
  loc=$(cmux --json tree --all | jq -r --arg s "$surface" '.windows[] | .ref as $win | .workspaces[]
    | .ref as $ws | .panes[] | .ref as $p | select(any(.. | objects; .ref? == $s)) | "\($win) \($ws) \($p)"' | head -n1)
  [ -n "$loc" ] || { echo "surface $surface of $1 not in the cmux tree"; return; }
  set -- $loc
  cmux focus-window --window "$1" >/dev/null && cmux select-workspace --workspace "$2" --window "$1" >/dev/null \
    && cmux focus-pane --pane "$3" --workspace "$2" --window "$1" >/dev/null && echo "jumped to $name"
}

# Anything that starts like a room ID counts as one, so a mistyped ID or a
# file name (ID.log) fails as "no room" instead of going out as a message.
is_id() { [[ $1 =~ ^[0-9]{8}-[0-9]{6}- ]]; }

# lc room: no argument (or "") opens the full-screen view (roomtui.py), one room ID
# opens that room, anything else sends a message. Without a terminal the view
# prints instead: the room list, or the thread of ID.
cmd_room() {
  local id=""
  # An empty message (lc room "") opens the view like no argument.
  [ $# -eq 1 ] && [ -z "$1" ] && shift
  if [ $# -gt 1 ] || { [ $# -eq 1 ] && ! is_id "$1"; }; then cmd_say "$@"; return; fi
  id="${1:-}"
  [ -z "$id" ] || [ -f "$ROOM_DIR/$id.log" ] || die "no room $id"
  if [ -t 0 ] && [ -t 1 ]; then
    mkdir -p "$ROOM_DIR"
    exec python3 "$(dirname "$0")/roomtui.py" "$ROOM_DIR" ${id:+"$id"}
  elif [ -n "$id" ]; then
    thread "$id" | show
  else
    rooms
  fi
}

case "${1:-}" in
  reply) shift; cmd_reply "$@" ;;
  room) shift; cmd_room "$@" ;;
  lanes) others_names=$(repo_lanes) || exit 1; printf '%s\n' "$others_names" | cut -f1 | sed '/^$/d' ;;
  go) shift; jump "${1:?usage: room.sh go NAME}" ;;
  *) die "usage: room.sh room|reply|lanes|go ..." ;;
esac
