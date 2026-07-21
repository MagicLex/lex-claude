#!/bin/zsh
# sonoflex autonomous learning pass (launchd: ai.sonoflex.learn).
# Mines recent transcripts for Lex's corrections, distills the recurring ones
# into the sonoflex identity's LC_LEARNED block, commits. No push, no gate.
# Canonical source: lex-claude/skills/sonoflex-learn/runner/run.sh
set -euo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

REPO="$HOME/.claude/lex-claude"
LOG_DIR="$HOME/.local/share/sonoflex-learn/logs"
LOCK="$HOME/.local/share/sonoflex-learn/.lock"
mkdir -p "$LOG_DIR"

# atomic lock (macOS ships no flock): mkdir succeeds only if the dir is absent
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "$(date) another pass holds the lock, skipping" >> "$LOG_DIR/skips.log"
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

cd "$REPO"
claude -p "/sonoflex-learn auto" \
  --model claude-sonnet-5 \
  --dangerously-skip-permissions \
  --max-turns 60 \
  >> "$LOG_DIR/$(date +%Y-%m-%d).log" 2>&1
