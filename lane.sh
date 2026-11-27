#!/usr/bin/env bash
# Start a new lane: a Claude session in a new cmux workspace at the repo root,
# whose first prompt is the lane kickoff with TASK filled in: team/LANE.md in a
# team-mode repo (lc team on), else the repo's docs/LANE.md.
#
#   lane.sh [--account main|alt|alt2|...] [TASK | -]
#   lane.sh - <<'EOF'
#   ...task...
#   EOF
#
# docs/LANE.md is the project's kickoff text; "{task}" in it is replaced by
# TASK, or by "open TODO work" without one. TASK "-" reads it from stdin: a
# task on the command line goes through the caller's shell, which runs its
# backticks and $( ) first, so quote the heredoc. Without --account the lane runs on
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
command -v cmux >/dev/null || die "cmux missing"
root=$(git rev-parse --show-toplevel 2>/dev/null) || die "run inside a git repo"
team="$(cd "$(dirname "$0")" && pwd)/team"
team_on=""
python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import team; sys.exit(0 if team.is_on() else 1)' "$team" 2>/dev/null && team_on=1
[ -n "$team_on" ] || [ -f "$root/docs/LANE.md" ] || die "no $root/docs/LANE.md and team mode is off: no kickoff text for a lane"

if [ "$*" = - ]; then
  task=$(cat)
  [ -n "${task//[[:space:]]/}" ] || die "empty task on stdin"
else
  task="${*:-open TODO work}"
fi
dir="$HOME/.claude/lex-claude/state/lane"; mkdir -p "$dir"
id=$(date +%Y%m%d-%H%M%S)-$$
if [ -n "$team_on" ]; then
  printf '%s' "$task" | python3 "$team/team.py" lane-prompt > "$dir/$id.prompt"
else
  TASK="$task" python3 -c 'import os,sys; sys.stdout.write(open(sys.argv[1]).read().replace("{task}", os.environ["TASK"]))' \
    "$root/docs/LANE.md" > "$dir/$id.prompt"
fi

{
  printf '#!/bin/bash\n'
  # A cmux started from a Claude session leaks the child-session marker into its shells.
  printf 'unset CLAUDECODE CLAUDE_CODE_CHILD_SESSION\n'
  if [ -n "${CLAUDE_CONFIG_DIR:-}" ]; then printf 'export CLAUDE_CONFIG_DIR=%q\n' "$CLAUDE_CONFIG_DIR"; else printf 'unset CLAUDE_CONFIG_DIR\n'; fi
  printf 'cd %q && exec /bin/zsh -lic %q\n' "$root" "lc claude \"\$(cat $(printf '%q' "$dir/$id.prompt"))\""
} > "$dir/$id.launch"
chmod +x "$dir/$id.launch"

CMUX_QUIET=1 bash "$(dirname "$0")/cmux-open.sh" "$root" lane "$task" "$dir/$id.launch" >/dev/null
echo "lane started in $(basename "$root"): $task"
