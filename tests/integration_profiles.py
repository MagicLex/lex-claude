#!/usr/bin/env python3
"""Replay a real Claude transcript under a separate account directory.

python3 tests/integration_profiles.py --transcript /path/to/session.jsonl
"""

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--transcript", required=True, type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
env = {key: value for key, value in os.environ.items()
       if not key.startswith(("LEX_CLAUDE_", "CLAUDE_CONFIG_DIR"))}
env["LEX_CLAUDE_RUNTIME"] = "claude"

with tempfile.TemporaryDirectory(prefix="lc profile's test ") as directory:
    work = Path(directory) / "project"
    work.mkdir()
    work = work.resolve()
    profile = Path(directory) / "account"
    transcript = profile / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(work)) / args.transcript.name
    transcript.parent.mkdir(parents=True)
    shutil.copyfile(args.transcript, transcript)

    def turn(config):
        return subprocess.run(
            ["bash", str(root / "succeed.sh"), "turn", transcript.stem],
            cwd=work, env={**env, "CLAUDE_CONFIG_DIR": str(config)},
            capture_output=True, text=True, timeout=10,
        )

    result = turn(profile)
    assert result.returncode == 0, result.stderr
    assert "USER: " in result.stdout, "Transcript did not render a user turn"
    other = turn(Path(directory) / "other-account")
    assert other.returncode == 1, other.stdout
    assert "no transcript" in other.stderr, other.stderr

print("PASS: alternate account transcript lookup and isolation")
