#!/usr/bin/env bash
# Files a gate request: the body comes on stdin and is written as is to
# <gate dir>/queue/<id>.md, with this session's "Lane: <name> <session id>"
# line (lc claim whoami) first unless the body has one. Quote the
# heredoc, or the shell runs the body's backticks and $( ) before it gets here:
#
#   lc gate file <id> <<'EOF'
#   ...request body...
#   EOF
#
# GATE_DIR defaults to gateDir in the repo's .claude/team.json. Refuses an id
# already in queue/ or done/ (a filed request is frozen: a change is a new id,
# team/TEAM.md, Gate queue), an empty body, and an empty Lane.
set -euo pipefail

TEAM="$(dirname "$0")/.."
GATE_DIR=${GATE_DIR:-$(python3 "$TEAM/team.py" config gateDir)}
[ -n "$GATE_DIR" ] || { echo "no gateDir in .claude/team.json and no GATE_DIR" >&2; exit 1; }
ID=${1:?usage: file.sh <id> < body}
ID=${ID%.md}
case $ID in */* | .* | "") echo "bad id: $ID" >&2; exit 1 ;; esac
filed() {
  local d
  for d in queue done; do
    [ ! -e "$GATE_DIR/$d/$ID.md" ] || { echo "$ID is already in $d/: a change is a new id (-rN)" >&2; return 0; }
  done
  return 1
}
! filed || exit 1

body=$(cat)
[ -n "${body//[[:space:]]/}" ] || { echo "empty body on stdin" >&2; exit 1; }
if ! printf '%s\n' "$body" | grep -E '^[-* ]*Lane: [^ ]+ [0-9A-Fa-f-]{36}' >/dev/null; then
  lane=$(python3 "$TEAM/claim.py" whoami)
  [[ $lane =~ ^[^\ ]+\ [0-9A-Fa-f-]{36}$ ]] || { echo "lc claim whoami gave no lane: '$lane'" >&2; exit 1; }
  body="Lane: $lane"$'\n\n'"$body"
fi

# Written aside and moved in, so the leash never names a half-written file.
mkdir -p "$GATE_DIR/queue"
tmp=$(mktemp "$GATE_DIR/.file-$ID.XXXXXX")
trap 'rm -f "$tmp"' EXIT
printf '%s\n' "$body" > "$tmp"
# The check and the move under one lock between filers, after stdin is read: a rival
# that filed this id meanwhile is in queue/ or, once reviewed, in done/. A kernel
# flock through perl (macOS has no flock command), its own file, not the leash's;
# it ends with this process.
exec 8>>"$GATE_DIR/file.flock"
perl -MFcntl=:flock -e 'open(my $fd, ">&=", 8) or die "$!"; alarm 30; exit(flock($fd, LOCK_EX) ? 0 : 1)' \
  || { echo "no filing lock within 30 s ($GATE_DIR/file.flock)" >&2; exit 1; }
! filed || exit 1
mv -n "$tmp" "$GATE_DIR/queue/$ID.md"
[ ! -e "$tmp" ] || { echo "$ID appeared in queue/ meanwhile" >&2; exit 1; }
echo "filed $GATE_DIR/queue/$ID.md"
