#!/usr/bin/env python3
"""Team mode on a scratch git repo: the switch, worktree sharing, config, lane
prompt, subagent brief hook, SessionStart hook and statusline, run as Claude
Code runs them.

  python3 tests/integration_team.py
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
TEAM = os.path.join(ROOT, "team", "team.py")
CONFIG = {
    "gateDir": "~/.scratch-team/gate",
    "firstReads": ["docs/PHILOSOPHY.md", "docs/TODO.md"],
    "resources": {"cluster": "the dev cluster"},
    "subagentBrief": ["Scratch repo rule for subagents."],
}


def sh(*cmd, cwd, stdin=None, env=None):
    return subprocess.run(cmd, cwd=cwd, input=stdin, capture_output=True, text=True, timeout=30,
                          env={**os.environ, **(env or {})})


class TeamMode(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = os.path.join(self.tmp, "scratch")
        os.makedirs(os.path.join(self.repo, ".claude"))
        with open(os.path.join(self.repo, ".claude", "team.json"), "w") as f:
            json.dump(CONFIG, f)
        for cmd in (["git", "init", "-q", "-b", "main"], ["git", "add", "-A"],
                    ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"]):
            self.assertEqual(sh(*cmd, cwd=self.repo).returncode, 0)
        self.worktree = os.path.join(self.tmp, "wt")
        self.assertEqual(sh("git", "worktree", "add", "-q", "-b", "w", self.worktree, cwd=self.repo).returncode, 0)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def team(self, *args, cwd=None, stdin=None):
        return sh("python3", TEAM, *args, cwd=cwd or self.repo, stdin=stdin)

    def agent_hook(self, cwd, prompt="Count the files."):
        event = {"tool_name": "Agent", "cwd": cwd,
                 "tool_input": {"description": "x", "prompt": prompt, "subagent_type": "general-purpose"}}
        out = sh("python3", os.path.join(ROOT, "team", "subagent-brief.py"), cwd=cwd, stdin=json.dumps(event))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stderr, "")
        return json.loads(out.stdout)["hookSpecificOutput"] if out.stdout.strip() else None

    def test_switch_is_shared_by_worktrees_and_untracked(self):
        self.assertIn("team: off", self.team().stdout)
        self.assertEqual(self.team("on").returncode, 0)
        self.assertIn("team: on", self.team(cwd=self.worktree).stdout)
        self.assertEqual(sh("git", "status", "--porcelain", cwd=self.repo).stdout, "")
        self.assertEqual(self.team("off", cwd=self.worktree).returncode, 0)
        self.assertIn("team: off", self.team().stdout)

    def test_on_needs_config(self):
        os.remove(os.path.join(self.worktree, ".claude", "team.json"))
        r = self.team("on", cwd=self.worktree)
        self.assertEqual(r.returncode, 1)
        self.assertIn("team.json", r.stderr)

    def test_alert(self):
        self.team("on")
        self.assertEqual(self.team("alert", "on").returncode, 0)
        self.assertIn("red alert: on", self.team(cwd=self.worktree).stdout)
        self.team("alert", "off")
        self.assertIn("red alert: off", self.team().stdout)

    def test_config_and_lane_prompt(self):
        self.assertEqual(self.team("config", "gateDir").stdout.strip(), os.path.expanduser("~/.scratch-team/gate"))
        prompt = self.team("lane-prompt", stdin="Fix the flaky test.").stdout
        self.assertIn(os.path.join(ROOT, "team", "TEAM.md"), prompt)
        self.assertIn("docs/PHILOSOPHY.md, docs/TODO.md", prompt)
        self.assertIn(os.path.expanduser("~/.scratch-team/gate"), prompt)
        self.assertTrue(prompt.rstrip().endswith("Task: Fix the flaky test."))
        self.assertNotIn("{", prompt)

    def test_subagent_brief_only_in_team_mode(self):
        self.assertIsNone(self.agent_hook(self.worktree))
        self.team("on")
        out = self.agent_hook(self.worktree)
        prompt = out["updatedInput"]["prompt"]
        self.assertEqual(out["permissionDecision"], "allow")
        self.assertTrue(prompt.startswith("Team subagent rules"))
        self.assertIn("- Scratch repo rule for subagents.", prompt)
        self.assertTrue(prompt.endswith("Count the files."))
        self.assertEqual(out["updatedInput"]["subagent_type"], "general-purpose")
        self.assertIsNone(self.agent_hook(self.worktree, prompt))

    def test_session_start_hook(self):
        env = {"CLAUDE_PROJECT_DIR": self.worktree}
        off = sh("bash", os.path.join(ROOT, "hook.sh"), cwd=self.worktree, env=env).stdout
        self.assertNotIn("===== team mode =====", off)
        self.team("on")
        on = sh("bash", os.path.join(ROOT, "hook.sh"), cwd=self.worktree, env=env).stdout
        self.assertIn("===== team mode =====", on)
        self.assertIn(os.path.join(ROOT, "team", "TEAM.md"), on)
        self.assertIn("persona", on)
        self.assertIn("(persona off: team mode)", on)
        self.assertIn("your session name and team role", on)

    def test_statusline(self):
        line = lambda: sh("bash", os.path.join(ROOT, "statusline-command.sh"), cwd=self.worktree,
                          stdin=json.dumps({"cwd": self.worktree, "session_id": "no-such-session"})).stdout
        self.assertNotIn(" lane", line())
        self.team("on")
        self.team("alert", "on")
        out = line()
        self.assertIn("\x1b[0;35mlane\x1b[0m", out)
        self.assertIn("RED ALERT", out)

    def verify(self, answer, cwd):
        path = os.path.join(self.tmp, "answer.txt")
        with open(path, "w") as f:
            f.write(answer)
        return sh("bash", os.path.join(ROOT, "master.sh"), "verify", "--answer", path, "--phase", "identity", cwd=cwd)

    def test_identity_judge_in_team_mode(self):
        # Runs the real judge (claude -p, haiku): a team successor names its session and the protocol, not the persona.
        self.team("on")
        team_answer = ("I am scratch-47, a lane in team mode under lex-claude team/TEAM.md; the identity persona is set aside. "
                       "I read the docs of every area I touch in full before acting, and own my work end to end. "
                       "The gate reviews every change: gate first for money, data, auth and shared clusters, land then audit for the rest. "
                       "Shared resources take a claim with lc claim before I change them. I work in a worktree from origin/main and never use git stash. "
                       "Tests run against real services, never mocks.")
        r = self.verify(team_answer, self.worktree)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        generic = "I am Claude, a helpful assistant. I have loaded my identity and I follow all my rules."
        self.assertEqual(self.verify(generic, self.worktree).returncode, 1)


if __name__ == "__main__":
    unittest.main()
