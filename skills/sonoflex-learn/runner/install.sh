#!/bin/zsh
# Install (or remove) the sonoflex-learn autonomous weekly runner.
# Opt-in on purpose: this schedules a headless `claude` pass that costs tokens,
# so it is NOT wired into `lc install`. Run it deliberately.
#
#   ./install.sh          install + load (idempotent)
#   ./install.sh --off    unload + remove
#
# macOS only (launchd). No-op with a message elsewhere.
set -euo pipefail

LABEL="ai.sonoflex.learn"
SRC="$HOME/.claude/lex-claude/skills/sonoflex-learn/runner/run.sh"
STATE_DIR="$HOME/.local/share/sonoflex-learn"
RUN_LINK="$STATE_DIR/run.sh"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

if [[ "$(uname)" != "Darwin" ]]; then
  echo "sonoflex-learn runner is launchd-only (macOS). Skipping on $(uname)."
  echo "On Linux, point a cron/systemd-timer at: $SRC"
  exit 0
fi

unload() {
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
}

if [[ "${1:-}" == "--off" ]]; then
  unload
  rm -f "$PLIST" "$RUN_LINK"
  echo "sonoflex-learn runner removed (launchd job unloaded, plist + link deleted)."
  echo "State kept: $STATE_DIR/logs, ledger, .last-learn."
  exit 0
fi

mkdir -p "$STATE_DIR/logs"
ln -sfn "$SRC" "$RUN_LINK"

cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>$RUN_LINK</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key>
    <integer>0</integer>
    <key>Hour</key>
    <integer>10</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardErrorPath</key>
  <string>$STATE_DIR/logs/launchd.err</string>
</dict>
</plist>
PL

plutil -lint "$PLIST" >/dev/null
unload
launchctl bootstrap "$DOMAIN" "$PLIST" 2>/dev/null || launchctl load "$PLIST"
echo "sonoflex-learn runner installed. Weekly, Sunday 10:00."
launchctl list | grep "$LABEL" || { echo "WARN: not registered"; exit 1; }
