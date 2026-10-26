#!/usr/bin/env python3
"""Replay a real Codex transcript through the CLI and hooks in an isolated home.

python3 tests/integration_codex.py --transcript /path/to/rollout.jsonl
"""

import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--transcript", required=True, type=Path)
args = parser.parse_args()
recording = args.transcript.read_text()
events = [json.loads(line) for line in recording.splitlines() if line.strip()]
meta = next(event for event in events if event.get("type") == "session_meta")
context = next(event for event in reversed(events) if event.get("type") == "turn_context")
count = next(event for event in reversed(events)
             if event.get("type") == "event_msg" and event.get("payload", {}).get("type") == "token_count"
             and event["payload"].get("info"))
expected = count["payload"]["info"]["last_token_usage"]["total_tokens"]


class CodexIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="lc codex's test ")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.sid = meta["payload"]["id"]
        self.path = self.home / ".codex/sessions/replay" / f"rollout-{self.sid}.jsonl"
        self.path.parent.mkdir(parents=True)
        self.path.write_text("\n".join(json.dumps(event) for event in (meta, context, count)) + "\n")
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("LEX_CLAUDE_", "LEX_CODEX_", "CODEX_"))}
        self.env.update(HOME=str(self.home), CODEX_HOME=str(self.home / ".codex"), CODEX_THREAD_ID=self.sid)
        cache = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "models_cache.json"
        if cache.exists():
            (self.home / ".codex/models_cache.json").write_bytes(cache.read_bytes())

    def set_usage(self, tokens, window=None):
        event = copy.deepcopy(count)
        event["payload"]["info"]["last_token_usage"]["total_tokens"] = tokens
        if window is not None:
            event["payload"]["info"]["model_context_window"] = window
        with self.path.open("a") as stream:
            stream.write(json.dumps(event) + "\n")

    def call(self, *command, data=None, env=None, success=True):
        result = subprocess.run([sys.executable, str(ROOT / "codex.py"), *command],
                                input=json.dumps(data) if data else None, capture_output=True,
                                text=True, env=env or self.env, timeout=10)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def hook(self, name="Stop", **fields):
        event = {"hook_event_name": name, "session_id": self.sid,
                 "transcript_path": str(self.path), **fields}
        return json.loads(self.call("hook", data=event).stdout)

    def test_measured_usage_and_explicit_session(self):
        result = json.loads(self.call("tokens", "--session", self.sid, "--json").stdout)
        self.assertEqual(result["context_tokens"], expected)
        self.assertEqual(result["total_tokens"], count["payload"]["info"]["total_token_usage"]["total_tokens"])
        self.assertEqual(result["model"], context["payload"]["model"])
        self.assertLess(result["handoff_threshold"], result["auto_compact_token_limit"])
        self.assertGreater(result["handoff_threshold"], result["model_context_window"] * 75 // 100)

    def test_configured_compaction_and_profile(self):
        config = self.home / ".codex/config.toml"
        config.write_text('model_auto_compact_token_limit = 100000\n')
        result = json.loads(self.call("tokens", "--json").stdout)
        self.assertEqual(result["auto_compact_token_limit"], 100000)
        self.assertEqual(result["handoff_threshold"], 95000)
        config.write_text('profile = "small"\nmodel_auto_compact_token_limit = 100000\n'
                          '[profiles.small]\nmodel_auto_compact_token_limit = 80000\n')
        result = json.loads(self.call("tokens", "--json").stdout)
        self.assertEqual(result["handoff_threshold"], 76000)

    def test_large_window_has_no_claude_cap(self):
        self.env["LEX_CLAUDE_HANDOFF_TOKENS"] = "1"
        self.set_usage(expected, window=828400)
        result = json.loads(self.call("tokens", "--json").stdout)
        self.assertGreater(result["handoff_threshold"], 600000)

    def test_unknown_window_does_not_trigger(self):
        event = copy.deepcopy(count)
        event["payload"]["info"]["model_context_window"] = None
        with self.path.open("a") as stream:
            stream.write(json.dumps(event) + "\n")
        self.assertEqual(self.hook(), {})
        self.assertIsNone(json.loads(self.call("tokens", "--json").stdout)["handoff_threshold"])

    def test_installed_cli_symlink_resolves_helper(self):
        install = self.home / ".claude/lex-claude"
        install.mkdir(parents=True)
        (install / "codex.py").symlink_to(ROOT / "codex.py")
        link = self.home / ".local/bin/lc"
        link.parent.mkdir(parents=True)
        link.symlink_to(ROOT / "bin/lex-claude")
        result = subprocess.run(["bash", str(link), "tokens", "--json"],
                                capture_output=True, text=True, env=self.env, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["context_tokens"], expected)

    def test_rate_limit_and_partial_records_do_not_erase_usage(self):
        with self.path.open("a") as stream:
            stream.write('\n' * 200 + '{"type":"event_msg","payload":{"type":"token_count","info":null}}\n{"type":')
        result = json.loads(self.call("tokens", "--json").stdout)
        self.assertEqual(result["context_tokens"], expected)

    def test_compaction_invalidates_old_usage(self):
        with self.path.open("a") as stream:
            stream.write('{"type":"compacted","payload":{}}\n')
        result = self.call("tokens", "--json", success=False)
        self.assertEqual(result.returncode, 1)
        self.assertIsNone(json.loads(result.stdout)["context_tokens"])
        self.assertEqual(self.hook(), {})

    def test_trigger_boundary_latch_and_continuation_guard(self):
        limit = json.loads(self.call("tokens", "--json").stdout)["handoff_threshold"]
        self.set_usage(limit - 1)
        self.assertEqual(self.hook(), {})
        self.set_usage(limit)
        self.assertEqual(self.hook(stop_hook_active=True), {})
        self.assertIn("additionalContext", self.hook("PostToolUse")["hookSpecificOutput"])
        self.assertEqual(self.hook("PostToolUse"), {})
        self.assertEqual(self.hook()["decision"], "block")
        self.assertEqual(self.hook(), {})

    def test_kill_switches_create_no_state(self):
        self.set_usage(count["payload"]["info"]["model_context_window"])
        for switch in ("LEX_CLAUDE_DISABLE", "LEX_CLAUDE_HANDOFF_DISABLE"):
            self.env[switch] = "1"
            self.assertEqual(self.hook(), {})
            self.env.pop(switch)
        self.assertFalse((self.home / ".claude").exists())

    def test_no_session_guess_and_no_cross_session_trigger(self):
        self.env.pop("CODEX_THREAD_ID")
        result = self.call("tokens", success=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("--session", result.stderr)
        self.set_usage(count["payload"]["info"]["model_context_window"])
        self.assertEqual(self.hook(session_id="00000000-0000-0000-0000-000000000000"), {})

    def test_success_suppresses_trigger(self):
        state = self.home / ".claude/lex-claude/state/.succession/codex"
        state.mkdir(parents=True)
        (state / f"{self.sid}.handed-off").touch()
        self.set_usage(count["payload"]["info"]["model_context_window"])
        self.assertEqual(self.hook(), {})
        self.assertEqual(self.hook("PostToolUse"), {})

    def test_wire_preserves_custom_config_and_is_idempotent(self):
        home = self.home / ".codex"
        config = '# retain this comment\n[tui]\nstatus_line = ["git-branch"]\n'
        (home / "config.toml").write_text(config)
        command = {"type": "command", "command": "python3 /other/codex.py hook"}
        (home / "hooks.json").write_text(json.dumps({"hooks": {"Stop": [{"hooks": [command]}]}}))
        self.call("wire")
        first = (home / "hooks.json").read_bytes()
        self.call("wire")
        self.assertEqual(first, (home / "hooks.json").read_bytes())
        self.assertEqual((home / "config.toml").read_text(), config)
        hooks = json.loads(first)["hooks"]
        self.assertEqual(hooks["Stop"][0]["hooks"][0], command)
        self.assertEqual(len(hooks["Stop"]), 2)

    def test_wire_adds_native_meter_to_existing_tui(self):
        import tomllib

        home = self.home / ".codex"
        (home / "config.toml").write_text('[tui] # retain\nnotifications = false\n[features]\nhooks = true\n')
        self.call("wire")
        config = tomllib.loads((home / "config.toml").read_text())
        self.assertFalse(config["tui"]["notifications"])
        self.assertIn("context-used", config["tui"]["status_line"])
        self.assertTrue(config["features"]["hooks"])


unittest.main(argv=[sys.argv[0]], verbosity=2)
