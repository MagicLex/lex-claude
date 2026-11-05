#!/bin/bash
# cmux-open.sh DIR NAME DESCRIPTION COMMAND
# Opens a cmux workspace in DIR running COMMAND, in the window that already holds a workspace of DIR's repo,
# else in a new window: one window per repo. Prints cmux's JSON for the new workspace.
set -euo pipefail
dir=$1 name=$2 desc=$3 command=$4
root=$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null || printf '%s' "$dir")

# The window of the first workspace whose directory is the repo or inside it.
window=$(cmux --json tree --all | ROOT="$root" python3 -c '
import json, os, subprocess, sys
root = os.environ["ROOT"].rstrip("/")
for w in json.load(sys.stdin)["windows"]:
    out = subprocess.run(["cmux", "--json", "workspace", "list", "--window", w["ref"]], capture_output=True, text=True)
    if out.returncode:
        continue
    for ws in json.loads(out.stdout)["workspaces"]:
        d = (ws.get("current_directory") or "").rstrip("/")
        if d == root or d.startswith(root + "/"):
            print(w["ref"]); sys.exit()
')

fresh=""
if [ -z "$window" ]; then
  window=$(cmux new-window --name "$name" | awk '{print $NF}')  # prints "OK <window id>"
  fresh=1
fi
made=$(cmux --json workspace create --window "$window" --name "$name" --description "$desc" \
  --cwd "$dir" --command "$command" --focus true)
if [ -n "$fresh" ]; then
  # A new window opens with a blank workspace, which may not be listed right after new-window returns. Once the real
  # one exists, close every other workspace of that window (being new, it holds nothing else); its shell may still be
  # starting, hence --force.
  MADE="$made" python3 -c '
import json, os, subprocess
made = json.loads(os.environ["MADE"])
out = subprocess.run(["cmux", "--json", "workspace", "list", "--window", made["window_ref"]], capture_output=True, text=True)
for ws in json.loads(out.stdout)["workspaces"] if out.returncode == 0 else []:
    if ws["ref"] != made["workspace_ref"]:
        subprocess.run(["cmux", "workspace", "close", "--force", ws["ref"]], capture_output=True)
'
fi
printf '%s\n' "$made"
