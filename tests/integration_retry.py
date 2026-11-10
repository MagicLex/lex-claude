#!/usr/bin/env python3
"""Run retry.sh as Claude Code does on a failed Bash call.

python3 tests/integration_retry.py
"""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]


def run(home, session, command, error):
    env = {**os.environ, "HOME": str(home)}
    env.pop("LEX_CLAUDE_DISABLE", None)
    event = {"session_id": session, "hook_event_name": "PostToolUseFailure", "tool_name": "Bash",
             "tool_input": {"command": command}, "error": error}
    result = subprocess.run(["bash", str(ROOT / "retry.sh")], input=json.dumps(event),
                            text=True, capture_output=True, env=env, timeout=10)
    return result


class Retry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.session = str(uuid.uuid4())

    def tearDown(self):
        self.tmp.cleanup()

    def test_same_failure_twice_warns(self):
        first = run(self.home, self.session, "make", "No rule to make target")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, "")
        second = run(self.home, self.session, "make", "No rule to make target")
        self.assertEqual(second.returncode, 0, second.stderr)
        context = json.loads(second.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Stop retrying", context)

    def test_different_error_stays_quiet(self):
        run(self.home, self.session, "make", "No rule to make target")
        result = run(self.home, self.session, "make", "Permission denied")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_other_session_stays_quiet(self):
        run(self.home, self.session, "make", "No rule to make target")
        result = run(self.home, str(uuid.uuid4()), "make", "No rule to make target")
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
