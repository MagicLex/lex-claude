#!/usr/bin/env bash
# Move live Claude Code sessions to another account, in their own herdr
# panes, so work survives one account hitting its usage limit.
#
#   move.sh --to main|alt|alt2|... [--dry-run] [<session-id>...]
#
# Accounts: main is ~/.claude, <name> is ~/.claude-<name>. Sources are every
# other account.
#
# Per session: link its transcript into the target account's projects dir (a
# symlink, so both accounts append to one file and the move can be reversed),
# stop the old process (its shell stays), then type the resume command into the
# same pane. Without ids, every live session of every other account moves.
# Sessions with no herdr pane are left running and get a printed resume line.
#
# Background agents, shells and monitors die with the old process; the kickoff
# prompt tells the resumed session to relaunch what it still needs.
set -euo pipefail

MAIN_DIR="$HOME/.claude"
ALT_DIR="${LEX_CLAUDE_ALT_DIR:-$HOME/.claude-alt}"
KICK="Moved to the other Claude account: the previous one hit its usage limit. Background agents, shells and monitors from before the move did not survive. Check which ones are still needed, relaunch them, then carry on with the work."

die() { echo "move: $*" >&2; exit 1; }

to="" dry=0 ids=()
while [ $# -gt 0 ]; do
  case "$1" in
    --to) to="${2:-}"; shift 2 ;;
    --dry-run) dry=1; shift ;;
    -*) die "unknown flag $1" ;;
    *) ids+=("$(printf '%s' "$1" | tr 'a-z' 'A-Z')"); shift ;;
  esac
done
acct_dir() { case "$1" in main) echo "$MAIN_DIR" ;; alt) echo "$ALT_DIR" ;; *) echo "$HOME/.claude-$1" ;; esac; }
case "$to" in
  "") die "usage: move.sh --to main|alt|alt2|... [--dry-run] [<session-id>...]" ;;
  # Unset, not set to ~/.claude: credentials are keyed on the config dir, so an
  # explicit default path would not find the main login.
  main) dst="$MAIN_DIR"; launch="env -u CLAUDE_CONFIG_DIR lex-claude claude" ;;
  *) dst=$(acct_dir "$to"); launch="CLAUDE_CONFIG_DIR=$dst lex-claude claude" ;;
esac
[ -d "$dst" ] || die "$dst missing; set up the account first (README: Additional Claude accounts)"
command -v jq >/dev/null || die "jq missing"
command -v herdr >/dev/null || die "herdr missing: no pane to resume in"

slug() { printf '%s' "$1" | sed 's#[^A-Za-z0-9]#-#g'; }

# This script's own ancestors: never stop the session that runs the move.
self=" "; p=$$
while [ "${p:-0}" -gt 1 ]; do self="$self$p "; p=$(ps -o ppid= -p "$p" | tr -d ' '); done

# Claude session id -> pane, from the session ids herdr's Claude hook reports.
panes=$(herdr agent list | jq -r '.result.agents[] | select(.agent == "claude")
  | "\(.agent_session.value // "" | ascii_upcase) \(.pane_id)"') || die "herdr agent list failed"

trusted() {  # trusted <config-dir> <cwd>: the cwd or a parent accepted the trust dialog
  local json="$1/.claude.json"; [ "$1" = "$MAIN_DIR" ] && json="$HOME/.claude.json"
  [ -f "$json" ] || return 1
  jq -e --arg d "$2" '[.projects // {} | to_entries[] | select(.value.hasTrustDialogAccepted == true)
    | .key as $k | select($d == $k or ($d | startswith($k + "/")))] | length > 0' "$json" >/dev/null 2>&1
}

srcs=()
for d in "$MAIN_DIR" "$ALT_DIR" "$HOME"/.claude-*; do
  [ -d "$d/sessions" ] && [ "$d" != "$dst" ] || continue
  case " ${srcs[*]-} " in *" $d "*) ;; *) srcs+=("$d") ;; esac
done

moved=0
for f in $(for d in "${srcs[@]-}"; do ls "$d"/sessions/*.json 2>/dev/null; done); do
  [ -f "$f" ] || continue
  src="${f%/sessions/*}"
  pid=$(jq -r '.pid // empty' "$f"); id=$(jq -r '.sessionId // empty' "$f" | tr 'a-z' 'A-Z')
  cwd=$(jq -r '.cwd // empty' "$f"); name=$(jq -r '.name // "?"' "$f")
  [ -n "$pid" ] && [ -n "$id" ] && [ -n "$cwd" ] && kill -0 "$pid" 2>/dev/null || continue
  case "$self" in *" $pid "*) continue ;; esac
  if [ ${#ids[@]} -gt 0 ]; then
    case " ${ids[*]} " in *" $id "*) ;; *) continue ;; esac
  fi
  pdir="$src/projects/$(slug "$cwd")"
  jsonl=$(ls "$pdir" 2>/dev/null | grep -ix "$id.jsonl" | head -1) || true
  [ -n "$jsonl" ] || { echo "skip $name: no transcript under $pdir"; continue; }
  sid="${jsonl%.jsonl}"   # on-disk case, as --resume expects
  pane=$(printf '%s\n' "$panes" | awk -v s="$id" '$1==s {print $2; exit}')
  if [ -z "$pane" ]; then
    echo "skip $name: no herdr pane. Stop it, then run in $cwd: $launch --resume $sid"
    continue
  fi
  if [ "$dry" = 1 ]; then echo "would move $name ($sid) on $pane"; continue; fi

  tdir="$dst/projects/$(slug "$cwd")"; mkdir -p "$tdir"
  [ -e "$tdir/$jsonl" ] || ln -s "$pdir/$jsonl" "$tdir/$jsonl"
  [ ! -d "$pdir/$sid" ] || [ -e "$tdir/$sid" ] || ln -s "$pdir/$sid" "$tdir/$sid"
  accept=0; trusted "$src" "$cwd" && ! trusted "$dst" "$cwd" && accept=1

  kill -TERM "$pid" 2>/dev/null || true
  for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
  if kill -0 "$pid" 2>/dev/null; then kill -KILL "$pid"; sleep 1; fi

  # A pane whose only process was claude closes with it.
  if ! herdr pane run "$pane" "$launch --resume $sid \"$KICK\"" >/dev/null 2>&1; then
    echo "FAIL $name ($sid): pane $pane is gone. Run in $cwd: $launch --resume $sid"
    continue
  fi

  # The target account asks for folder trust once per project. Accept it only
  # when the source account already trusts that folder.
  ok=0
  for _ in $(seq 1 45); do
    screen=$(herdr pane read "$pane" --source recent --lines 40 2>/dev/null || true)
    if [ "$accept" = 1 ] && printf '%s' "$screen" | grep -q "Yes, I trust this folder"; then
      herdr pane send-keys "$pane" Down >/dev/null
      herdr pane send-keys "$pane" Enter >/dev/null
      accept=0
    fi
    if jq -r '.sessionId // empty' "$dst"/sessions/*.json 2>/dev/null | grep -qix "$sid"; then ok=1; break; fi
    sleep 2
  done
  if [ "$ok" = 1 ]; then echo "moved $name ($sid) to $to on $pane"; moved=$((moved+1))
  else echo "FAIL $name ($sid): not running under $dst after 90s; check $pane"; fi
done
[ "$dry" = 1 ] || echo "$moved session(s) moved to $to."
