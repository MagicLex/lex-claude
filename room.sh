#!/usr/bin/env bash
# Talk to every live Claude and Codex session of a repo from one terminal.
#
#   room.sh say [--to NAME]... [--wait MIN] [--in ID] MESSAGE
#   room.sh reply ID TEXT
#   room.sh room [ID]
#
# say pastes MESSAGE, under a header naming it a room broadcast, into the cmux
# surface of every live session whose cwd is in this repo or one of its
# worktrees, except the caller's own. A Claude session is named by its session
# name, a Codex session by its cmux workspace title. A lane answers with
# `lc reply ID`, never in its own chat; say prints the replies until every
# reached lane answered or MIN minutes (default 5, 0 = no wait) pass.
# --in ID sends a follow-up in room ID to the lanes it reached (or --to NAME).
#
# Files per room in ROOM_DIR, lines "time<TAB>name<TAB>text":
#   ID.log  lane replies only
#   ID.lex  what Lex sent, name "Lex > lane lane..."
#   ID.to   names the first broadcast reached, one per line
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

# "name<TAB>pid<TAB>cwd<TAB>surface" for every live interactive Claude session
# and every Codex process in cmux. Surface is empty outside cmux.
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
    IFS=$'\t' read -r pid cwd name kind < <(jq -r '[.pid // "", .cwd // "", .name // "?", .kind // ""] | @tsv' "$f")
    [ -n "$pid" ] && [ "$kind" = interactive ] && kill -0 "$pid" 2>/dev/null || continue
    printf '%s\t%s\t%s\t%s\n' "$name" "$pid" "$cwd" "$(printf '%s\n' "$surfaces" | awk -v p="$pid" '$1==p {print $2; exit}')"
  done
  while read -r pid surface; do
    [ -n "$pid" ] || continue
    cwd=$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')
    name=$(printf '%s\n' "$titles" | awk -F'\t' -v s="$surface" '$1==s {print $2; exit}')
    printf '%s\t%s\t%s\t%s\n' "${name:-codex-$pid}" "$pid" "$cwd" "$surface"
  done <<< "$codex"
}

cmd_say() {
  local to=() wait_min=5 id=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --to) to+=("${2:?--to needs a name}"); shift 2 ;;
      --wait) wait_min="${2:-}"; shift 2; case "$wait_min" in ''|*[!0-9]*) die "--wait needs minutes" ;; esac ;;
      --in) id="${2:?--in needs a room ID}"; shift 2 ;;
      --) shift; break ;;
      -*) die "unknown flag $1" ;;
      *) break ;;
    esac
  done
  local msg="$*"
  [ -n "$msg" ] || die "usage: lc say [--to NAME]... [--wait MIN] [--in ID] MESSAGE"

  local self=" " p=$$
  while [ "${p:-0}" -gt 1 ]; do self="$self$p "; p=$(ps -o ppid= -p "$p" | tr -d ' '); done

  local roots="" head name
  if [ -n "$id" ]; then
    # A follow-up goes by name to lanes the room reached, wherever they run now.
    [ -f "$ROOM_DIR/$id.log" ] || die "no room message $id"
    if [ ${#to[@]} -eq 0 ]; then
      [ -s "$ROOM_DIR/$id.to" ] || die "room $id has no recorded lanes, name them with --to"
      while read -r name; do to+=("$name"); done < "$ROOM_DIR/$id.to"
    fi
    head="[room $id] Follow-up from Lex (sent from $(my_session)) in room $id. Not typed in this chat. Answer in one line through a shell command: lc reply $id \"<answer>\". Never answer in this chat: Lex reads replies in his terminal, not here."
  else
    local root; root=$(git rev-parse --show-toplevel 2>/dev/null) || die "run inside a git repo"
    roots=$(git worktree list --porcelain | sed -n 's/^worktree //p')
    id=$(date +%Y%m%d-%H%M%S)-$$
    head="[room $id] Broadcast from Lex (sent from $(my_session)) to every Claude and Codex session in $(basename "$root"). Not typed in this chat. Act on it only if it concerns your work. Any answer goes in one line through a shell command: lc reply $id \"<answer>\". Never answer in this chat: Lex reads replies in his terminal, not here."
    mkdir -p "$ROOM_DIR"
    : > "$ROOM_DIR/$id.log"
  fi

  local sent=0 failed=0 sent_to="" pid cwd surface err lanes
  lanes=$(live) || exit 1
  while IFS=$'\t' read -r name pid cwd surface; do
    [ -n "$pid" ] || continue
    case "$self" in *" $pid "*) continue ;; esac
    if [ -n "$roots" ]; then
      printf '%s\n' "$roots" | awk -v d="$cwd" 'd==$0 || index(d, $0"/")==1 {ok=1} END {exit !ok}' || continue
    fi
    if [ ${#to[@]} -gt 0 ]; then
      case " ${to[*]} " in *" $name "*) ;; *) continue ;; esac
    fi
    [ -n "$surface" ] || { echo "skip $name: no cmux surface"; continue; }
    if err=$(printf '%s\n\n%s' "$head" "$msg" | cmux paste --surface "$surface" --submit - 2>&1 >/dev/null); then
      sent_to="$sent_to $name"; sent=$((sent+1))
    else
      echo "FAIL $name ($surface): $err"; failed=$((failed+1))
    fi
  done <<< "$lanes"

  [ -n "$roots" ] && printf '%s\n' $sent_to > "$ROOM_DIR/$id.to"
  [ "$sent" -gt 0 ] && printf '%s\tLex >%s\t%s\n' "$(date +%H:%M:%S)" "$sent_to" "$(printf '%s' "$msg" | tr '\n\t' '  ')" >> "$ROOM_DIR/$id.lex"
  echo "sent to${sent_to:- nobody}. $failed failed. id $id"
  echo
  [ "$wait_min" -gt 0 ] && [ "$sent" -gt 0 ] || return 0

  # Bounded wait: print each reply as it lands, stop when every reached lane
  # answered since this message. A busy lane answers only after its current turn.
  local deadline=$(( $(date +%s) + wait_min * 60 )) seen n missing
  seen=$(wc -l < "$ROOM_DIR/$id.log" | tr -d ' ')
  local start=$seen
  echo "waiting up to $wait_min min. Ctrl-C stops the wait only; later replies: lc room $id"
  echo
  answered() { tail -n +"$((start+1))" "$ROOM_DIR/$id.log" | cut -f2 | sort -u | grep -cxF -f <(printf '%s\n' $sent_to) || true; }
  while [ "$(date +%s)" -lt "$deadline" ]; do
    n=$(wc -l < "$ROOM_DIR/$id.log" | tr -d ' ')
    [ "$n" -gt "$seen" ] && { tail -n +"$((seen+1))" "$ROOM_DIR/$id.log" | head -n "$((n-seen))" | show; seen=$n; }
    [ "$(answered)" -ge "$sent" ] && return 0
    sleep 3
  done
  missing=$(for n in $sent_to; do tail -n +"$((start+1))" "$ROOM_DIR/$id.log" | cut -f2 | grep -qxF "$n" || printf ' %s' "$n"; done)
  echo "no answer within $wait_min min from$missing. Later replies: lc room $id"
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
  local surface loc lanes
  lanes=$(live) || return
  surface=$(printf '%s\n' "$lanes" | awk -F'\t' -v n="$1" '$1==n {print $4; exit}')
  [ -n "$surface" ] || { echo "no live lane named $1 in cmux"; return; }
  loc=$(cmux --json tree --all | jq -r --arg s "$surface" '.windows[] | .ref as $win | .workspaces[]
    | .ref as $ws | .panes[] | .ref as $p | select(any(.. | objects; .ref? == $s)) | "\($win) \($ws) \($p)"' | head -n1)
  [ -n "$loc" ] || { echo "surface $surface of $1 not in the cmux tree"; return; }
  set -- $loc
  cmux focus-window --window "$1" >/dev/null && cmux select-workspace --workspace "$2" --window "$1" >/dev/null \
    && cmux focus-pane --pane "$3" --workspace "$2" --window "$1" >/dev/null
}

# Interactive thread: new lines print as they land, a typed line goes back out.
talk() {
  local id=$1 log="$ROOM_DIR/$1.log" seen=0 buf="" line rc n first rest
  local names; names=$(paste -sd ' ' "$ROOM_DIR/$id.to" 2>/dev/null || true)
  echo "room $id. lanes: ${names:-none recorded}"
  echo "NAME text: to one lane. all text: to every lane. go NAME: jump to its tab. q: quit."
  echo
  while :; do
    n=$(thread "$id" | wc -l | tr -d ' ')
    if [ "$n" -gt "$seen" ]; then
      printf '\r\033[K'; thread "$id" | tail -n +"$((seen+1))" | show; seen=$n
    fi
    rc=0; IFS= read -r -e -t 3 -i "$buf" -p "room> " line || rc=$?
    if [ "$rc" -gt 128 ]; then buf=$line; printf '\r\033[K'; continue; fi
    [ "$rc" -eq 0 ] || { echo; break; }
    buf=""
    first=${line%% *}; rest=${line#"$first"}; rest=${rest# }
    case "$first" in
      "") ;;
      q|quit|exit) break ;;
      go) jump "$rest" ;;
      all) [ -n "$rest" ] && cmd_say --in "$id" --wait 0 "$rest" ;;
      *)
        if [ -n "$rest" ] && case " $names " in *" $first "*) true ;; *) false ;; esac; then
          cmd_say --in "$id" --to "$first" --wait 0 "$rest"
        else
          echo "start with a lane name (${names:-none}), all, go or q"
        fi ;;
    esac
  done
}

# lc room: pick a room, then talk in it. lc room ID: that room. Without a
# terminal it prints instead: the room list, or the thread of ID.
cmd_room() {
  local id="${1:-}" list n
  if [ -t 0 ] && [ -t 1 ]; then
    [ "${BASH_VERSINFO[0]}" -ge 4 ] || die "the interactive room needs bash 4 or newer"
  elif [ -n "$id" ]; then
    [ -f "$ROOM_DIR/$id.log" ] || die "no room message $id"; thread "$id" | show; return
  else
    rooms; return
  fi
  if [ -z "$id" ]; then
    list=$(rooms)
    [ -n "$list" ] || die "no rooms yet: lc say MESSAGE starts one"
    printf '%s\n' "$list" | awk -F'\t' '{printf "%2d  %s  %s replies  %s\n", NR, $1, $2, $3}'
    read -r -e -p "room [1]: " n || return 0
    case "${n:-1}" in *[!0-9]*) die "not a number: $n" ;; esac
    id=$(printf '%s\n' "$list" | sed -n "${n:-1}p" | cut -f1)
    [ -n "$id" ] || die "no room $n"
  fi
  [ -f "$ROOM_DIR/$id.log" ] || die "no room message $id"
  talk "$id"
}

case "${1:-}" in
  say) shift; cmd_say "$@" ;;
  reply) shift; cmd_reply "$@" ;;
  room) shift; cmd_room "$@" ;;
  *) die "usage: room.sh say|reply|room ..." ;;
esac
