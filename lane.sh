#!/usr/bin/env bash
# Start a new lane: a Claude session in a new herdr workspace at the repo root,
# whose first prompt is the repo's docs/LANE.md with TASK filled in.
#
#   lane.sh [--account main|alt|alt2|...] [TASK]
#
# docs/LANE.md is the project's kickoff text; "{task}" in it is replaced by
# TASK, or by "open TODO work" without one. Without --account the lane runs on
# the caller's account (CLAUDE_CONFIG_DIR).
set -euo pipefail

die() { echo "lane: $*" >&2; exit 1; }
if [ "${1:-}" = --account ]; then
  case "${2:-}" in
    "") die "--account needs main, alt, alt2, ..." ;;
    # Unset, not ~/.claude: credentials are keyed on the config dir.
    main) unset CLAUDE_CONFIG_DIR ;;
    *) CLAUDE_CONFIG_DIR="$HOME/.claude-$2"; [ -d "$CLAUDE_CONFIG_DIR" ] || die "$CLAUDE_CONFIG_DIR missing" ;;
  esac
  shift 2
fi
command -v herdr >/dev/null || die "herdr missing"
command -v jq >/dev/null || die "jq missing"
root=$(git rev-parse --show-toplevel 2>/dev/null) || die "run inside a git repo"
[ -f "$root/docs/LANE.md" ] || die "no $root/docs/LANE.md: the kickoff text for a lane"

task="${*:-open TODO work}"
dir="$HOME/.claude/lex-claude/state/lane"; mkdir -p "$dir"
id=$(date +%Y%m%d-%H%M%S)-$$
TASK="$task" python3 -c 'import os,sys; sys.stdout.write(open(sys.argv[1]).read().replace("{task}", os.environ["TASK"]))' \
  "$root/docs/LANE.md" > "$dir/$id.prompt"

{
  printf '#!/bin/bash\n'
  # A herdr server started from a Claude session leaks that session's CLAUDE_*
  # variables into every pane. A child-session marker stops the transcript.
  printf 'for v in $(compgen -e); do case $v in CLAUDE_CONFIG_DIR) ;; CLAUDECODE|CLAUDE_*) unset "$v" ;; esac; done\n'
  if [ -n "${CLAUDE_CONFIG_DIR:-}" ]; then printf 'export CLAUDE_CONFIG_DIR=%q\n' "$CLAUDE_CONFIG_DIR"; else printf 'unset CLAUDE_CONFIG_DIR\n'; fi
  printf 'cd %q && exec /bin/zsh -lic %q\n' "$root" "lc claude \"\$(cat $(printf '%q' "$dir/$id.prompt"))\""
} > "$dir/$id.launch"
chmod +x "$dir/$id.launch"

# The launcher runs in the workspace's own shell, so the pane outlives claude
# (lc move types the resume command into it).
pane=$(herdr workspace create --cwd "$root" --label lane --focus | jq -r '.result.root_pane.pane_id // empty')
[ -n "$pane" ] || die "herdr workspace create failed"
herdr pane run "$pane" "$(printf '%q' "$dir/$id.launch")" >/dev/null || die "herdr pane run $pane failed"
echo "lane started in $(basename "$root"): $task"
