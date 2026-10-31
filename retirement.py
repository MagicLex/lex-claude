#!/usr/bin/env python3
"""Retire a verified predecessor after its successor resumes in another terminal."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import uuid


def root(runtime):
    return Path.home() / ".claude/lex-claude/state/.succession/retirement" / runtime


def sid(value):
    return str(uuid.UUID(value))


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        json.dump(data, stream)
        stream.write("\n")
    os.replace(stream.name, path)


def ps(pid):
    result = subprocess.run(["ps", "-p", str(pid), "-o", "ppid=,lstart=,tty=,comm="],
                            capture_output=True, text=True, timeout=5)
    fields = result.stdout.strip().split(None, 7)
    if len(fields) != 8:
        return None
    return {"pid": int(pid), "ppid": int(fields[0]), "started": " ".join(fields[1:6]),
            "tty": fields[6], "command": fields[7]}


def same_process(saved):
    current = ps(saved["pid"])
    return current is not None and all(current[k] == saved[k] for k in ("pid", "started", "command", "tty"))


HERDR_ERRORS = (OSError, subprocess.SubprocessError, ValueError, KeyError)


def herdr(*args):
    result = subprocess.run(["herdr", *args], capture_output=True, text=True, check=True, timeout=5)
    # Some commands (pane run) print nothing on success.
    return json.loads(result.stdout)["result"] if result.stdout.strip() else {}


def binding(runtime, session):
    candidates = set()
    codex_session = os.environ.get("CODEX_THREAD_ID")
    if runtime == "claude":
        directory = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")))
        for path in (directory / "sessions").glob("*.json"):
            try:
                info = json.loads(path.read_text())
                if str(info.get("sessionId", "")).lower() == session:
                    candidates.add(int(path.stem))
            except (OSError, ValueError):
                continue
    elif codex_session and codex_session.lower() != session:
        return {"process": None, "pane": None, "terminal": None}
    pid = os.getppid()
    process = None
    for _ in range(32):
        item = ps(pid)
        if not item or pid <= 1:
            break
        if pid in candidates or (runtime == "codex" and codex_session == session and
                                 Path(item["command"]).name == "codex"):
            process = item
            break
        pid = item["ppid"]
    pane = os.environ.get("HERDR_PANE_ID") or None
    # Pane ids restart with the herdr server; the terminal id tells panes apart.
    # Unknown terminal: the handover is not acknowledged and no pane is closed.
    terminal = None
    if pane:
        try:
            terminal = herdr("pane", "get", pane)["pane"]["terminal_id"]
        except HERDR_ERRORS:
            pass
    return {"process": process, "pane": pane, "terminal": terminal}


def register(runtime, parent, successor):
    parent, successor = sid(parent), sid(successor)
    if parent == successor:
        raise ValueError("a successor must differ from its predecessor")
    path = root(runtime) / f"{parent}.json"
    if path.exists():
        saved = json.loads(path.read_text())
        if saved.get("ready"):
            raise ValueError("this predecessor has already handed off")
    write(path, {"parent": parent, "successor": successor, "target": binding(runtime, parent),
                 "ready": False, "closed": False})
    write(root(runtime) / f"{successor}.parent", {"parent": parent})


def pane_owns(target, process):
    """The recorded pane still exists, is the same terminal, and runs the process's tty."""
    try:
        pane = herdr("pane", "get", target["pane"])["pane"]
        shell = herdr("pane", "process-info", "--pane", target["pane"])["process_info"]["shell_pid"]
    except HERDR_ERRORS:
        return False
    shell = ps(shell)
    return (pane["terminal_id"] == target["terminal"] and shell is not None and
            shell["tty"] == process["tty"] and process["tty"] != "??")


def close_target(target):
    process = target.get("process")
    if not process or not same_process(process):
        return False
    if target.get("pane"):
        if not pane_owns(target, process):
            raise RuntimeError("predecessor process no longer belongs to its recorded herdr pane")
        # Closing a workspace's last pane closes the workspace.
        herdr("pane", "close", target["pane"])
    # A closed terminal may leave a process that ignores SIGHUP.
    for sig in (signal.SIGTERM, signal.SIGKILL):
        if not same_process(process):
            return True
        os.kill(process["pid"], sig)
        for _ in range(10):
            if not same_process(process):
                return True
            time.sleep(0.1)
    raise RuntimeError("predecessor process did not exit")


def retire(runtime, parent):
    path = root(runtime) / f"{sid(parent)}.json"
    with path.with_suffix(".lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        saved = json.loads(path.read_text())
        if not saved.get("ready") or saved.get("closed"):
            return
        try:
            saved["closed"] = close_target(saved["target"])
            if not saved["closed"]:
                saved["error"] = "predecessor process unavailable; terminal left untouched"
            else:
                saved.pop("error", None)
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            saved["error"] = str(error)
        write(path, saved)


def launch_retirement(runtime, parent, target=None):
    directory = root(runtime)
    with (directory / f"{parent}.log").open("a") as log:
        command = (["close", runtime, json.dumps(target)] if target else ["retire", runtime, parent])
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), *command],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)


def hook(runtime, event):
    if any(os.environ.get(key) == "1" for key in ("LEX_CLAUDE_DISABLE", "LEX_CLAUDE_HANDOFF_DISABLE")):
        return {}
    session = sid(event["session_id"])
    directory = root(runtime)
    parent_path = directory / f"{session}.parent"
    if parent_path.exists():
        parent = json.loads(parent_path.read_text())["parent"]
        path = directory / f"{parent}.json"
        saved = json.loads(path.read_text())
        current = binding(runtime, session)
        target = saved["target"]
        # Verification subprocesses inherit the parent's terminal. Only a live
        # resume in another process and pane acknowledges the handover.
        if (saved["successor"] == session and current["process"] and target["process"] and
                current["process"]["pid"] != target["process"]["pid"] and
                (not target.get("terminal") or
                 (current["terminal"] and current["terminal"] != target["terminal"]))):
            if not saved["ready"]:
                saved["ready"] = True
                saved["successor_target"] = current
                write(path, saved)
            if not saved["closed"]:
                launch_retirement(runtime, parent)
    path = directory / f"{session}.json"
    if path.exists():
        saved = json.loads(path.read_text())
        if saved.get("ready"):
            reason = f"Session retired. Verified successor: {saved['successor']}. Do not resume work here."
            current = binding(runtime, session)
            successor = saved.get("successor_target", {})
            if (current["process"] and current["terminal"] != successor.get("terminal") and
                    current["process"]["pid"] != successor.get("process", {}).get("pid")):
                launch_retirement(runtime, session, current)
            if event.get("hook_event_name") == "PreToolUse":
                return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                        "permissionDecision": "deny", "permissionDecisionReason": reason}}
            return {"continue": False, "stopReason": reason}
    return {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("hook", "register", "retire", "close"))
    parser.add_argument("runtime", choices=("claude", "codex"))
    parser.add_argument("ids", nargs="*")
    args = parser.parse_args()
    if args.command == "hook":
        print(json.dumps(hook(args.runtime, json.load(sys.stdin))))
    elif args.command == "register":
        register(args.runtime, *args.ids)
    elif args.command == "retire":
        retire(args.runtime, *args.ids)
    else:
        close_target(json.loads(args.ids[0]))


if __name__ == "__main__":
    main()
