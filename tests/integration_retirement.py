#!/usr/bin/env python3
"""Replay Claude/Codex hooks against disposable processes and real herdr panes.

python3 tests/integration_retirement.py
No model requests are made. Session registry records are test inputs.
"""

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import retirement


def herdr(*args):
    return retirement.herdr(*args)


def workspace_ids():
    return {w["workspace_id"] for w in herdr("workspace", "list")["workspaces"]}


def worker(runtime, role, directory, parent, child):
    home = Path(directory)
    os.environ["HOME"] = str(home)
    os.environ["CLAUDE_CONFIG_DIR"] = str(home / ".claude")
    os.environ.pop("LEX_CLAUDE_DISABLE", None)
    os.environ.pop("LEX_CLAUDE_HANDOFF_DISABLE", None)
    session = child if role == "child" else parent
    os.environ["CODEX_THREAD_ID"] = session
    registry = home / ".claude/sessions"
    registry.mkdir(parents=True, exist_ok=True)
    # A Codex session is found through its "codex" process, the worker's parent.
    pid = os.getppid() if runtime == "codex" else os.getpid()
    if runtime == "claude":
        (registry / f"{pid}.json").write_text(json.dumps({"sessionId": session}))
    pane = os.environ["HERDR_PANE_ID"]
    info = {"process": retirement.ps(pid), "pane": pane,
            "terminal": herdr("pane", "get", pane)["pane"]["terminal_id"]}
    if role == "parent":
        subprocess.run([sys.executable, str(ROOT / "retirement.py"), "register", runtime, parent, child], check=True)
    else:
        event = {"session_id": session, "hook_event_name": "SessionStart"}
        result = subprocess.run([sys.executable, str(ROOT / "retirement.py"), "hook", runtime],
                                input=json.dumps(event), text=True, capture_output=True, check=True)
        info["hook"] = json.loads(result.stdout)
    retirement.write(home / f"{role}.json", info)
    time.sleep(120)


def wait_for(check):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.1)
    raise AssertionError("Timed out waiting for the disposable terminal")


class RetirementIntegration(unittest.TestCase):
    def test_unrelated_session_cannot_bind_to_caller(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("HERDR_")}
        result = subprocess.run(
            [sys.executable, "-c", "import json, retirement, uuid; "
             "print(json.dumps(retirement.binding('codex', str(uuid.uuid4()))))"],
            cwd=ROOT, env=env, capture_output=True, text=True, check=True, timeout=10)
        self.assertIsNone(json.loads(result.stdout)["process"])

    def exercise(self, runtime, sibling=False):
        with tempfile.TemporaryDirectory(prefix="lc-retirement-test-") as directory:
            home = Path(directory)
            parent, child = str(uuid.uuid4()), str(uuid.uuid4())
            workspaces = []
            existing = workspace_ids()
            # A process named codex: retirement binds a Codex session by name.
            codex = home / "codex"
            codex.symlink_to("/bin/bash")

            def launch(role):
                command = shlex.join([sys.executable, str(Path(__file__).resolve()), "--worker",
                                      runtime, role, directory, parent, child])
                if runtime == "codex":
                    # A trailing command keeps bash from exec'ing into python.
                    command = shlex.join([str(codex), "-c", command + "; exit $?"])
                result = herdr("workspace", "create", "--cwd", directory,
                               "--label", f"lc-test-{runtime}-{role}", "--no-focus")
                workspace, pane = result["workspace"]["workspace_id"], result["root_pane"]["pane_id"]
                self.assertNotIn(workspace, existing)
                workspaces.append(workspace)
                herdr("pane", "run", pane, "exec " + command)
                return {"workspace_id": workspace, "pane_id": pane}

            state = home / ".claude/lex-claude/state/.succession/retirement" / runtime / f"{parent}.json"
            try:
                launched = launch("parent")
                wait_for(lambda: (home / "parent.json").exists())
                target = json.loads((home / "parent.json").read_text())
                self.assertEqual(target["pane"], launched["pane_id"])
                self.assertEqual(json.loads(state.read_text())["target"], target)
                self.assertTrue(retirement.same_process(target["process"]))
                self.assertFalse(json.loads(state.read_text())["ready"])
                if sibling:
                    neighbor = herdr("pane", "split", launched["pane_id"], "--direction", "right",
                                     "--no-focus")["pane"]["pane_id"]
                    herdr("pane", "run", neighbor, "exec /bin/sleep 120")
                    wrong = dict(target, pane=neighbor,
                                 terminal=herdr("pane", "get", neighbor)["pane"]["terminal_id"])
                    with self.assertRaisesRegex(RuntimeError, "no longer belongs"):
                        retirement.close_target(wrong)
                    self.assertTrue(retirement.same_process(target["process"]))
                stale = dict(target, process=dict(target["process"], started="not this process"))
                self.assertFalse(retirement.close_target(stale))
                launch("child")
                wait_for(lambda: json.loads(state.read_text())["closed"])
                self.assertFalse(retirement.same_process(target["process"]))
                wait_for(lambda: (home / "child.json").exists())
                successor = json.loads((home / "child.json").read_text())
                self.assertTrue(retirement.same_process(successor["process"]))
                if sibling:
                    panes = herdr("pane", "list", "--workspace", launched["workspace_id"])["panes"]
                    self.assertEqual([p["pane_id"] for p in panes], [neighbor])
                env = {k: v for k, v in os.environ.items() if not k.startswith(("HERDR_", "LEX_CLAUDE_"))}
                env["HOME"] = str(home)
                event = {"session_id": parent, "hook_event_name": "PreToolUse"}
                result = subprocess.run([sys.executable, str(ROOT / "retirement.py"), "hook", runtime],
                                        input=json.dumps(event), env=env, text=True, capture_output=True, check=True)
                self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")
                revived = launch("revived")
                wait_for(lambda: revived["workspace_id"] not in workspace_ids())
                self.assertTrue(retirement.same_process(successor["process"]))
            finally:
                for workspace in workspaces:
                    self.assertNotIn(workspace, existing)
                    subprocess.run(["herdr", "workspace", "close", workspace],
                                   capture_output=True, timeout=10)

    def test_claude_acknowledgement_retirement_and_revive_guard(self):
        self.exercise("claude")

    def test_codex_retirement_preserves_sibling_pane(self):
        self.exercise("codex", sibling=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker(*sys.argv[2:])
    else:
        unittest.main(verbosity=2)
