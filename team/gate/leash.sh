#!/usr/bin/env bash
# Keeps the gate working through <gate dir>/queue/. The queue folder is the state:
# a request is open while its file sits in queue/, and done once the gate has
# written "<id>: PASS|FIX|REJECT" in verdicts.md and moved the file to done/
# (id = the file name without .md). The gate's cmux inbox is only a doorbell.
#
# Every INTERVAL the leash names the oldest open request to the gate, again at
# most every NUDGE_EVERY for the same one. A request open longer than OVERDUE is
# listed in <gate dir>/overdue.txt and raised as a desktop notification.
#
# Alerts ring the memory lane (the session with role memory, lc team role, else
# the cmux workspace whose title says "memory", or GATE_LEASH_MEMORY) and lanes with open requests, once per key, recorded in
# <gate dir>/alerted.txt: when the gate cannot be reached (its surface is gone,
# or every send fails for STUCK), the memory lane and every open request's
# lane, once per outage; when a request turns overdue, the memory lane and
# that request's lane, once per request.
#
# Each round it also rings the lane of every request newly in done/ with its
# verdict word, so a lane whose wait died still learns it. The lane is the name
# on the request's "Lane: <name> <session id>" line, or the live name of that id.
# Rung ids go to <gate dir>/rung.txt (seeded with done/ on first run, so a
# restart rings nothing old); a failed ring is retried RING_TRIES rounds.
#
#   lc gate leash        (from the repo's main checkout; GATE_DIR defaults to its gateDir)
set -uo pipefail

TEAM="$(cd "$(dirname "$0")/.." && pwd)"
GATE_DIR=${GATE_DIR:-$(python3 "$TEAM/team.py" config gateDir)}
[ -n "$GATE_DIR" ] || { echo "no gateDir in .claude/team.json and no GATE_DIR" >&2; exit 1; }
INTERVAL=${GATE_LEASH_INTERVAL:-10}
NUDGE_EVERY=${GATE_LEASH_NUDGE_EVERY:-600}
OVERDUE=${GATE_LEASH_OVERDUE:-1800}
RING_TRIES=${GATE_LEASH_RING_TRIES:-3}
STUCK=${GATE_LEASH_STUCK:-900}
C=$(command -v cmux || echo /Applications/cmux.app/Contents/Resources/bin/cmux)
LC=$(command -v lc || echo "$HOME/.local/bin/lc")
# lc keys its room by the current directory: only the main checkout reaches the
# lanes, never a worktree.
REPO=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")
export CMUX_QUIET=1

mkdir -p "$GATE_DIR/queue" "$GATE_DIR/done"
# One leash per gate dir: a kernel flock (taken through perl, macOS has no flock
# command) on fd 9. It lasts while an open fd 9 refers to it and ends with the
# leash, so a dead leash leaves no stale lock. Long-lived children close fd 9
# (9>&-), or an orphaned sleep would keep the lock after a kill.
LOCK="$GATE_DIR/leash.flock"
exec 9>>"$LOCK"
if ! perl -MFcntl=:flock -e 'open(my $fd, ">&=", 9) or die "$!"; exit(flock($fd, LOCK_EX | LOCK_NB) ? 0 : 1)'; then
  echo "a leash already runs for $GATE_DIR (pid $(cat "$LOCK"))" >&2
  exit 1
fi
echo $$ > "$LOCK"

log() { echo "$(date -u +%H:%M:%SZ) $*"; }

RUNG="$GATE_DIR/rung.txt"
TRIES="$GATE_DIR/ring-tries.txt"
ALERTED="$GATE_DIR/alerted.txt"
ALERT_TRIES="$GATE_DIR/alert-tries.txt"
[ -e "$RUNG" ] || ls "$GATE_DIR/done" | sed -n 's/\.md$//p' > "$RUNG"
touch "$TRIES" "$ALERTED" "$ALERT_TRIES"

# The lane of a request file: its "Lane:" line, else its first line.
lane_of() {
  local f=$1 lane sid now_name
  lane=$(sed -n 's/^[-* ]*Lane: *\([^ ]*\).*/\1/p' "$f" | head -1)
  # A session moved to another account or terminal keeps its id and gets a new name.
  sid=$(sed -n 's/^[-* ]*Lane:.*\([0-9A-Fa-f]\{8\}-[0-9A-Fa-f-]\{27\}\).*/\1/p' "$f" | head -1)
  if [ -n "$sid" ] && now_name=$(cd "$REPO" && python3 "$TEAM/claim.py" name "$sid" 2>/dev/null) && [ "$now_name" != "$lane" ]; then
    log "${f#"$GATE_DIR"/}: Lane $lane is $now_name now (session $sid)" >&2
    lane=$now_name
  fi
  printf '%s' "$lane"
}

# ring <lane> <text>: sends through lc room; RING_OUT holds lc's answer. lc
# prints "sent to <name>. 0 failed.", or "sent to <name>, <name>. 0 failed."
# when two live sessions share the name.
RING_OUT=""
ring() {
  RING_OUT=$(cd "$REPO" && timeout 60 "$LC" room --to "$1" --wait 0 "$2" </dev/null 2>&1 9>&-) \
    && printf '%s\n' "$RING_OUT" | grep -E "^sent to $1(,? $1)*\. 0 failed\." >/dev/null
}

memory_lane() {
  [ -n "${GATE_LEASH_MEMORY:-}" ] && { printf '%s' "$GATE_LEASH_MEMORY"; return; }
  local mem
  mem=$(cd "$REPO" && python3 "$TEAM/team.py" who memory 2>/dev/null 9>&- | head -1)
  [ -n "$mem" ] || mem=$("$C" workspace list 2>/dev/null 9>&- | grep -i 'memory' | grep -oE "$(basename "$REPO")-[0-9a-z]+" | head -1)
  printf '%s' "$mem"
}

# alert <key> <lane> <text>: rings once per key and lane, retried up to RING_TRIES rounds.
alert() {
  local key="$1 $2" n
  grep -qxF "$key" "$ALERTED" && return
  if ring "$2" "$3"; then
    log "alerted $2: $1"
    echo "$key" >> "$ALERTED"
    return
  fi
  echo "$key" >> "$ALERT_TRIES"
  n=$(grep -cxF "$key" "$ALERT_TRIES")
  if [ "$n" -ge "$RING_TRIES" ]; then
    log "gave up alerting $2 for $1 after $n tries: $RING_OUT"
    echo "$key" >> "$ALERTED"
  else
    log "alert $n/$RING_TRIES for $1 to $2 failed: $RING_OUT"
  fi
}

ring_verdicts() {
  local id f lane word n
  while IFS= read -r id; do
    f="$GATE_DIR/done/$id.md"
    RING_OUT=""
    lane=$(lane_of "$f")
    if [ -z "$lane" ]; then
      log "no lane in done/$id.md, not rung"
      echo "$id" >> "$RUNG"
      continue
    fi
    # The verdict word, read as wait.sh reads it. Two live sessions with one name both get the ring: "sent to <name> <name>".
    word=$(awk -v id="$id" '
      /^[^ ]+( [0-9a-f]+)?: (PASS|FIX|REJECT)/ && index($0, id ": ") == 1 { v = $2; sub(/[^A-Z]+$/, "", v); print v; exit }' "$GATE_DIR/verdicts.md")
    if [ -n "$word" ] && ring "$lane" "gate: $id: $word. Entry in $GATE_DIR/verdicts.md."; then
      log "rang $lane: $id $word"
      echo "$id" >> "$RUNG"
      continue
    fi
    echo "$id" >> "$TRIES"
    n=$(grep -cxF "$id" "$TRIES")
    if [ "$n" -ge "$RING_TRIES" ]; then
      log "gave up ringing $lane for $id after $n tries: ${word:-no verdict line} $RING_OUT"
      echo "$id" >> "$RUNG"
    else
      log "ring $n/$RING_TRIES for $id to $lane failed: ${word:-no verdict line} $RING_OUT"
    fi
  done < <(comm -23 <(ls "$GATE_DIR/done" | sed -n 's/\.md$//p' | sort) <(sort -u "$RUNG"))
}

last_id=""
last_nudge=0
last_overdue=""
last_err=""
# The first failed send of the current outage; 0 while sends succeed.
fail_since=0
while :; do
  ring_verdicts
  now=$(date +%s)
  open=()
  while IFS= read -r f; do open+=("$f"); done < <(ls -tr "$GATE_DIR"/queue/*.md 2>/dev/null)
  if [ "${#open[@]}" -gt 0 ]; then
    id=$(basename "${open[0]}" .md)
    if [ "$id" != "$last_id" ] || [ $((now - last_nudge)) -ge "$NUDGE_EVERY" ]; then
      surf=$(cat "$GATE_DIR/GATE_SURFACE" 2>/dev/null)
      err="no surface in GATE_SURFACE"
      if [ -n "$surf" ] && err=$("$C" paste --surface "$surf" --submit "Leash: ${#open[@]} open in queue/. Next: queue/$id.md. When reviewed, write \"$id: PASS\" (or FIX, REJECT) as the first line of its entry in verdicts.md, then move queue/$id.md to done/. After a context compaction, re-read $GATE_DIR/BRIEF.md first." 2>&1 >/dev/null 9>&-); then
        log "named $id to the gate, ${#open[@]} open"
        last_id=$id
        last_nudge=$now
        fail_since=0
        last_err=""
      else
        # cmux refuses while someone types in the gate's prompt or a dialog is open; the next round retries.
        [ "$err" = "$last_err" ] || log "not sent to the gate: $err"
        last_err=$err
        [ "$fail_since" -gt 0 ] || fail_since=$now
        # A gone surface does not come back; a refused paste may be someone typing, so it waits STUCK.
        if printf '%s' "$err" | grep -E 'no surface in GATE_SURFACE|Missing or invalid terminal_id|Terminal surface not found' >/dev/null \
            || [ $((now - fail_since)) -ge "$STUCK" ]; then
          msg="gate: unreachable since $(date -u -r "$fail_since" +%H:%MZ), ${#open[@]} request(s) unsent ($err). The memory lane restarts it (team/TEAM.md, Gate queue)."
          mem=$(memory_lane)
          if [ -n "$mem" ]; then alert "down-$fail_since" "$mem" "$msg"; else log "no memory lane to alert"; fi
          # One alert per lane per round, so a lane with several requests keeps RING_TRIES rounds.
          seen=" $mem "
          for f in "${open[@]}"; do
            lane=$(lane_of "$f")
            [ -n "$lane" ] && [[ $seen != *" $lane "* ]] || continue
            seen+="$lane "
            alert "down-$fail_since" "$lane" "$msg Yours: $(basename "$f" .md)."
          done
        fi
      fi
    fi
    overdue=""
    for f in "${open[@]}"; do
      # The gate may have moved it to done/ since the listing.
      mtime=$(stat -f %m "$f" 2>/dev/null) || continue
      age=$((now - mtime))
      [ "$age" -ge "$OVERDUE" ] || continue
      oid=$(basename "$f" .md)
      overdue+="$oid $((age / 60)) min"$'\n'
      msg="gate: $oid open $((age / 60)) min, past $((OVERDUE / 60)) min."
      mem=$(memory_lane)
      [ -n "$mem" ] && alert "overdue-$oid" "$mem" "$msg"
      lane=$(lane_of "$f")
      [ -n "$lane" ] && [ "$lane" != "$mem" ] && alert "overdue-$oid" "$lane" "$msg The memory lane is rung."
    done
    printf '%s' "$overdue" > "$GATE_DIR/overdue.txt"
    # Ages change every minute: compare the ids only.
    overdue_ids=$(printf '%s' "$overdue" | cut -d' ' -f1)
    if [ -n "$overdue" ] && [ "$overdue_ids" != "$last_overdue" ]; then
      n=$(printf '%s' "$overdue" | grep -c .)
      osascript -e "display notification \"$n gate request(s) open past $((OVERDUE / 60)) min: see overdue.txt\" with title \"$(basename "$REPO") gate\"" >/dev/null 2>&1 9>&- || true
      log "overdue: $(printf '%s' "$overdue" | tr '\n' ';')"
    fi
    last_overdue=$overdue_ids
  else
    : > "$GATE_DIR/overdue.txt"
    last_id=""
    last_overdue=""
  fi
  sleep "$INTERVAL" 9>&-
done
