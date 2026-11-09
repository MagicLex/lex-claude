#!/usr/bin/env bash
# Keep every Claude account's MCP servers in step with mcp.json.
#
#   mcp.sh             report, per account: claude.ai user, each expected
#                      connector, missing local servers. Exit 1 on any gap.
#   mcp.sh fix [ACCT]  add missing local servers, then walk the connector gaps
#                      in the agent Chrome, logged in as the account's user.
#
# Accounts: main is ~/.claude (config in ~/.claude.json), <name> is
# ~/.claude-<name>. Connectors (Gmail, Drive, ...) belong to the claude.ai
# user, so they are connected on claude.ai as that user, never through /mcp:
# its OAuth opens whatever claude.ai login the browser holds.
#
# Connector state comes from claude.ai (remote_servers_with_connection), read
# in the agent Chrome, so only for the user that browser is logged in as.
# `claude mcp list` is the fallback for the other accounts: in 2.1.319 it
# reported Google Docs "Connected" for a user claude.ai shows as not connected,
# so its "ok" is printed as "ok?". Its "auth" and absent are real gaps.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPEC="${LEX_CLAUDE_MCP_SPEC:-$HERE/mcp.json}"
CONNECTORS_URL="https://claude.ai/customize/connectors"
POLL_SECS=10 POLL_MAX=60   # waits: 60 polls of 10s = 10 min
export AGENT_BROWSER_SESSION=lc-mcp   # own tab binding, other sessions' tabs untouched

die() { echo "mcp: $*" >&2; exit 1; }
command -v jq >/dev/null || die "jq missing"
command -v claude >/dev/null || die "claude missing"
[ -f "$SPEC" ] || die "$SPEC missing"
B=$(command -v agent-browser-bg || command -v agent-browser || true)

acct_dir() { case "$1" in main) echo "$HOME/.claude" ;; *) echo "$HOME/.claude-$1" ;; esac; }
acct_json() { case "$1" in main) echo "$HOME/.claude.json" ;; *) echo "$HOME/.claude-$1/.claude.json" ;; esac; }
# Unset, not set to ~/.claude, for main: credentials are keyed on the config dir.
acct_claude() {
  local a="$1"; shift
  if [ "$a" = main ]; then env -u CLAUDE_CONFIG_DIR claude "$@"
  else CLAUDE_CONFIG_DIR="$(acct_dir "$a")" claude "$@"; fi
}
accounts() {
  [ -f "$HOME/.claude.json" ] && echo main
  local d
  for d in "$HOME"/.claude-*/; do
    d="${d%/}"; [ -f "$d/.claude.json" ] && echo "${d##*/.claude-}"
  done
}
email() { jq -r '.oauthAccount.emailAddress // "?"' "$(acct_json "$1")"; }
org() { jq -r '.oauthAccount.organizationUuid // ""' "$(acct_json "$1")"; }

tmp=$(mktemp -d)
tab=""
cleanup() { [ -z "$tab" ] || "$B" tab close "$tab" >/dev/null 2>&1 || true; rm -rf "$tmp"; }
trap cleanup EXIT
trap 'exit 130' INT TERM HUP PIPE

# One claude.ai tab for the whole run: fetch() needs the claude.ai origin.
open_tab() {
  [ -n "$B" ] || return 1
  [ -n "$tab" ] && return 0
  "$B" tab new --label lc-mcp "$CONNECTORS_URL" >/dev/null 2>&1 || return 1
  tab=lc-mcp
  sleep 3
}
js() { "$B" eval "$1" 2>/dev/null | tail -1 | jq -r 'if type == "string" then . else tostring end' 2>/dev/null; }
browser_email() {
  js '(async()=>{try{const r=await fetch("/api/account");return r.ok?(await r.json()).email_address:""}catch(e){return ""}})()'
}

# Writes $tmp/<acct>: "name<TAB>state" per claude.ai connector the user has,
# state ok, ok? (CLI only) or auth.
probe_api() {
  js "(async()=>{const r=await fetch('/api/organizations/$(org "$1")/mcp/remote_servers_with_connection');
    if(!r.ok)return '';const j=await r.json();
    return (Array.isArray(j)?j:j.data||[]).map(s=>s.name+'\t'+(s.connection_state==='connected'?'ok':'auth')).join('\n')})()" > "$tmp/$1"
}
probe_cli() {
  (cd "$HOME" && acct_claude "$1" mcp list 2>/dev/null) \
    | sed -n 's/^claude\.ai \(.*\): .* - \(.*\)$/\1	\2/p' \
    | sed 's/	✔ Connected$/	ok?/; s/	! Needs authentication$/	auth/' > "$tmp/$1"
}

missing_servers() {
  jq -r --slurpfile have "$(acct_json "$1")" \
    '($have[0].mcpServers // {}) as $h | .servers | keys[] | select(. as $n | $h | has($n) | not)' "$SPEC"
}
# Prints "kind<TAB>name<TAB>state" per expected item that is not plain ok.
# Needs a probe of the account first.
status() {
  local a="$1" c state
  while IFS= read -r c; do
    state=$(awk -F'\t' -v n="$c" '$1 == n { print $2 }' "$tmp/$a")
    [ "$state" = ok ] || printf 'connector\t%s\t%s\n' "$c" "${state:-absent}"
  done < <(jq -r '.connectors[]' "$SPEC")
  missing_servers "$a" | awk '{ printf "server\t%s\tmissing\n", $0 }'
}
gaps() { status "$1" | awk -F'\t' '$3 != "ok?"'; }

report() {
  local a rc=0 s n who="" src
  open_tab && who=$(browser_email)
  for a in "$@"; do [ "$(email "$a")" = "$who" ] || probe_cli "$a" & done; wait
  for a in "$@"; do
    src="claude mcp list"
    [ "$(email "$a")" = "$who" ] && { probe_api "$a"; src="claude.ai"; }
    s=$(gaps "$a")
    printf '%-6s %s (connectors via %s)\n' "$a" "$(email "$a")" "$src"
    [ -z "$s" ] || { rc=1; printf '%s\n' "$s" | awk -F'\t' '{ printf "       %-9s %-15s %s\n", $1, $2, $3 }'; }
    n=$(status "$a" | awk -F'\t' '$3 == "ok?"' | wc -l | tr -d ' ')
    [ "$n" = 0 ] || echo "       $n connectors ok? (claude mcp list, unverified)"
    [ -n "$s" ] || [ "$n" != 0 ] || echo "       ok"
  done
  [ -n "$who" ] || echo "agent Chrome not on claude.ai: no connector state verified on claude.ai"
  return $rc
}

# Claude Code caches "needs authentication" per connector and skips cached ones
# at session start, so a connector fixed on claude.ai stays hidden until the
# entry goes. Drops the entries of expected connectors, which are ok now.
clear_cache() {
  local f; f="$(acct_dir "$1")/mcp-needs-auth-cache.json"
  [ -f "$f" ] || return 0
  jq --slurpfile spec "$SPEC" 'with_entries(select(.key | ltrimstr("claude.ai ") as $n | $spec[0].connectors | index($n) | not))' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
}

fix() {
  local a="$1" want got i g
  open_tab || die "agent Chrome unreachable (lc doctor)"
  want=$(email "$a")

  while IFS= read -r name; do
    acct_claude "$a" mcp add-json -s user "$name" "$(jq -c --arg n "$name" '.servers[$n]' "$SPEC")" >/dev/null
    echo "$a: added local server $name"
  done < <(missing_servers "$a")

  got=$(browser_email)
  if [ "$got" != "$want" ]; then
    echo "$a: agent Chrome is on claude.ai as '${got:-nobody}'. Log out and log in as $want in that window."
    for ((i = 0; i < POLL_MAX; i++)); do
      sleep "$POLL_SECS"; got=$(browser_email)
      [ "$got" = "$want" ] && break
    done
    [ "$got" = "$want" ] || die "$a: still not logged in as $want; run 'lc mcp fix $a' again"
  fi
  # The web acts in its last active org; the account's connectors live in its own.
  "$B" eval "document.cookie='lastActiveOrg=$(org "$a"); path=/; domain=.claude.ai; max-age=31536000'" >/dev/null 2>&1
  "$B" open "$CONNECTORS_URL" >/dev/null 2>&1

  probe_api "$a"; g=$(gaps "$a")
  [ -n "$g" ] || { clear_cache "$a"; echo "$a: ok"; return 0; }
  echo "$a: connect these on $CONNECTORS_URL (agent Chrome, as $want):"
  cut -f2,3 <<< "$g" | sed 's/^/  /'
  for ((i = 0; i < POLL_MAX; i++)); do
    sleep "$POLL_SECS"; probe_api "$a"
    [ -n "$(gaps "$a")" ] || { clear_cache "$a"; echo "$a: ok"; return 0; }
  done
  echo "$a: still missing after $((POLL_SECS * POLL_MAX))s:"
  gaps "$a" | cut -f2,3 | sed 's/^/  /'
  return 1
}

case "${1:-}" in
  "") report $(accounts) ;;
  fix)
    if [ -n "${2:-}" ]; then
      [ -f "$(acct_json "$2")" ] || die "no account $2"
      fix "$2"
    else
      rc=0; for a in $(accounts); do fix "$a" || rc=1; done; exit $rc
    fi ;;
  *) die "usage: mcp.sh [fix [ACCOUNT]]" ;;
esac
