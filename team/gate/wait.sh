#!/usr/bin/env bash
# Waits for the gate's verdict on one request and prints it. The request is
# done once <gate dir>/done/<id>.md exists (leash.sh). Exit 0 PASS, 2 FIX,
# 3 REJECT, 1 still open after the wait.
#
#   lc gate wait <id> [seconds, default 1800]
# GATE_DIR defaults to gateDir in the repo's .claude/team.json.
set -euo pipefail

GATE_DIR=${GATE_DIR:-$(python3 "$(dirname "$0")/../team.py" config gateDir)}
[ -n "$GATE_DIR" ] || { echo "no gateDir in .claude/team.json and no GATE_DIR" >&2; exit 1; }
ID=${1:?usage: wait.sh <id> [seconds]}
ID=${ID%.md}
deadline=$((SECONDS + ${2:-1800}))
until [ -e "$GATE_DIR/done/$ID.md" ]; do
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "$ID: still open in queue/ (leash: $GATE_DIR/overdue.txt)" >&2
    exit 1
  fi
  left=$((deadline - SECONDS))
  sleep $((left < 15 ? left : 15))
done
# The verdict entry: from its "<id>: VERDICT" heading to the next heading.
verdict=$(awk -v id="$ID" '
  /^[^ ]+( [0-9a-f]+)?: (PASS|FIX|REJECT)/ { on = (index($0, id ": ") == 1); if (on && !v) { v = $2; sub(/[^A-Z]+$/, "", v) } }
  on { print }
  END { if (v) print "VERDICT " v }' "$GATE_DIR/verdicts.md")
printf '%s\n' "$verdict" | grep -v '^VERDICT ' || true
case $(printf '%s\n' "$verdict" | sed -n 's/^VERDICT //p') in
  PASS) exit 0 ;;
  FIX) exit 2 ;;
  REJECT) exit 3 ;;
  *) echo "$ID is in done/ but verdicts.md has no \"$ID: PASS|FIX|REJECT\" line" >&2; exit 1 ;;
esac
