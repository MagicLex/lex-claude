#!/usr/bin/env python3
"""Run digest.sh as Claude Code does and check exit status and output.

python3 tests/integration_digest.py
"""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]


def run(home, cwd, session):
    env = {**os.environ, "HOME": str(home), "LEX_CLAUDE_DIGEST_EVERY": "1"}
    env.pop("LEX_CLAUDE_DISABLE", None)
    event = {"session_id": session, "cwd": str(cwd), "hook_event_name": "UserPromptSubmit", "prompt": "hi"}
    return subprocess.run(["bash", str(ROOT / "digest.sh")], input=json.dumps(event),
                          text=True, capture_output=True, env=env, timeout=10)


class Digest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.project = Path(self.tmp.name) / "project"
        self.project.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_project_without_team_rules(self):
        result = run(self.home, self.project, str(uuid.uuid4()))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("rules digest", result.stdout)
        self.assertNotIn("Team rules", result.stdout)

    def test_project_with_team_rules(self):
        (self.project / "docs").mkdir()
        (self.project / "docs/TEAM.md").write_text("# Team\n")
        result = run(self.home, self.project, str(uuid.uuid4()))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Team rules: re-read", result.stdout)


if __name__ == "__main__":
    unittest.main()
