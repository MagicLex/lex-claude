#!/usr/bin/env python3
"""Codex hooks, measured context usage, and persisted successor sessions."""

import argparse
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
import time


def codex_home():
    return Path(os.environ.get("CODEX_HOME") or os.environ.get("CODEX_DIR") or Path.home() / ".codex")


def state_dir():
    return Path.home() / ".claude/lex-claude/state/.succession/codex"


def session_id(value):
    import uuid

    return str(uuid.UUID(value))


def records(path, reverse=False):
    def backwards(stream):
        stream.seek(0, 2)
        position = stream.tell()
        pending = b""
        while position:
            size = min(position, 65536)
            position -= size
            stream.seek(position)
            lines = (stream.read(size) + pending).split(b"\n")
            pending = lines[0]
            yield from reversed(lines[1:])
        if pending:
            yield pending

    with Path(path).open("rb") as stream:
        for line in backwards(stream) if reverse else stream:
            try:
                value = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue  # A running session may still be writing its last record.
            if isinstance(value, dict):
                yield value


def transcript(sid):
    sid = session_id(sid)
    paths = list((codex_home() / "sessions").glob(f"**/*{sid}.jsonl"))
    if len(paths) != 1:
        raise ValueError(f"expected one Codex transcript for {sid}, found {len(paths)}")
    return paths[0]


def usage(path):
    result = {"context_tokens": None, "model_context_window": None, "total_tokens": None}
    first = next(records(path), {})
    if first.get("type") == "session_meta":
        result.update(session_id=first["payload"].get("id"), cwd=first["payload"].get("cwd"))
    found_usage = False
    found_context = False
    for record in records(path, reverse=True):
        payload = record.get("payload", {})
        if record.get("type") == "turn_context" and not found_context:
            found_context = True
            for key in ("model", "effort", "approval_policy", "sandbox_policy"):
                if key in payload:
                    result[key] = payload[key]
        elif record.get("type") == "compacted" and not found_usage:
            found_usage = True
        elif not found_usage and record.get("type") == "event_msg" and payload.get("type") == "token_count":
            info = payload.get("info")
            if not isinstance(info, dict):
                continue  # Rate-limit-only events have no usage update.
            found_usage = True
            last = info.get("last_token_usage") or {}
            # Cached input is already part of input_tokens. Lifetime usage is
            # cumulative and cannot measure the remaining context window.
            result["context_tokens"] = last.get("total_tokens")
            result["model_context_window"] = info.get("model_context_window")
            result["total_tokens"] = (info.get("total_token_usage") or {}).get("total_tokens")
        if found_usage and found_context:
            break
    result["transcript_path"] = str(path)
    return result


def positive_env(name, default):
    value = int(os.environ.get(name, default))
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def threshold(data):
    limit = compaction_limit(data)
    if limit is None:
        return None
    percent = positive_env("LEX_CODEX_HANDOFF_PERCENT", 95)
    if percent >= 100:
        raise ValueError("LEX_CODEX_HANDOFF_PERCENT must be below 100")
    return max(1, limit * percent // 100)


def compaction_limit(data):
    import tomllib

    window = data.get("model_context_window")
    if not isinstance(window, int) or window <= 0:
        return None
    cache = codex_home() / "models_cache.json"
    models = json.loads(cache.read_text()).get("models", []) if cache.exists() else []
    model = next((m for m in models if m.get("slug") == data.get("model")), {})
    config_path = codex_home() / "config.toml"
    config = tomllib.loads(config_path.read_text()) if config_path.exists() else {}
    profile = config.get("profiles", {}).get(config.get("profile"), {})
    config.update(profile)
    # Codex 0.164.0: ModelInfo::auto_compact_token_limit uses 90% of the
    # raw window; token_count reports usable_context_window (95% by default).
    effective = model.get("effective_context_window_percent", 95)
    if not isinstance(effective, int) or not 0 < effective <= 100:
        return None
    limit = window * 90 // effective
    configured = config.get("model_auto_compact_token_limit", model.get("auto_compact_token_limit"))
    if isinstance(configured, int) and configured > 0:
        limit = min(limit, configured)
    return limit


def disabled():
    return any(os.environ.get(key) == "1" for key in ("LEX_CLAUDE_DISABLE", "LEX_CLAUDE_HANDOFF_DISABLE"))


def render_turn(path):
    lines = []
    for record in records(path, reverse=True):
        item = record.get("payload", {})
        if record.get("type") != "response_item":
            continue
        if item.get("type") == "message" and item.get("role") in ("user", "assistant"):
            text = "\n".join(part.get("text", "") for part in item.get("content", []))
            lines.append(item["role"].upper() + ": " + text)
            if item["role"] == "user":
                break
        elif item.get("type") in ("function_call", "custom_tool_call"):
            lines.append(f"[tool {item.get('name')}] " + str(item.get("arguments", item.get("input", "")))[:240])
    return "\n".join(reversed(lines))[:9000]


def watch(sid, path):
    saved_path = state_dir() / f"{sid}.json"
    if not saved_path.exists():
        return None
    saved = json.loads(saved_path.read_text())
    if not saved.get("briefing") or saved.get("watch_left", 0) <= 0:
        return None
    saved["watch_left"] -= 1
    saved_path.write_text(json.dumps(saved, indent=2) + "\n")
    with tempfile.TemporaryDirectory(prefix="lc-codex-watch-") as tmp:
        answer = Path(tmp) / "turn.txt"
        briefing = Path(tmp) / "briefing.txt"
        answer.write_text(render_turn(path))
        briefing.write_text(saved["briefing"])
        verdict = verify(answer, "trajectory", briefing)
    with saved_path.with_suffix(".log").open("a") as log:
        log.write(json.dumps(verdict) + "\n")
    if verdict["pass"] is False:
        return {"decision": "block", "reason": "Succession watch: " + verdict["reason"] +
                ". Follow the latest user instruction; otherwise correct course against the briefing."}
    return None


def hook(event):
    if disabled():
        return {}
    sid = session_id(event["session_id"])
    name = event["hook_event_name"]
    import retirement
    retired = retirement.hook("codex", event)
    if retired:
        return retired
    if name == "SessionStart":
        text = f"Codex context usage: lc tokens --session {sid}. Handoffs use lc-succession's Codex path."
        lineage = state_dir() / f"{sid}.json"
        if lineage.exists():
            saved = json.loads(lineage.read_text())
            text += f" Successor generation {saved['generation']}, predecessor {saved['parent']}."
        return {"hookSpecificOutput": {"hookEventName": name, "additionalContext": text}}
    if name not in ("PostToolUse", "Stop") or event.get("stop_hook_active"):
        return {}
    path = Path(event["transcript_path"]) if event.get("transcript_path") else transcript(sid)
    data = usage(path)
    if data.get("session_id") != sid:
        return {}
    if name == "Stop":
        correction = watch(sid, path)
        if correction:
            return correction
    tokens = data.get("context_tokens")
    limit = threshold(data)
    if limit is None or not isinstance(tokens, int) or tokens < limit:
        return {}
    root = state_dir()
    root.mkdir(parents=True, exist_ok=True)
    if (root / f"{sid}.handed-off").exists():
        return {}
    marker = root / f"{sid}.{name}"
    try:
        with marker.open("x"):
            pass
    except FileExistsError:
        return {}
    reason = (f"HANDOFF DUE: Codex context at {tokens} tokens; handoff threshold {limit}. "
              "Invoke lc-succession using its Codex instructions. Compose a live briefing, "
              "run succeed.sh --runtime codex run, and relay the verified resume command. "
              "Do not continue the task in this session after a successful handoff.")
    if name == "Stop":
        return {"decision": "block", "reason": reason}
    return {"hookSpecificOutput": {"hookEventName": name, "additionalContext": reason}}


def bounded_run(command, **kwargs):
    timeout = kwargs.get("timeout", positive_env("LEX_CODEX_SUCCESSION_TIMEOUT", 180))
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, start_new_session=True, env=kwargs.get("env")) as process:
        try:
            stdout, stderr = process.communicate(kwargs.get("input"), timeout=timeout)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            raise
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def codex_exec(prompt, output, *, resume=None, model=None, effort=None, ephemeral=False, neutral=False):
    command = ["codex", "exec", "--json", "--skip-git-repo-check",
               "-c", 'sandbox_mode="read-only"', "-c", 'approval_policy="never"',
               "-c", "features.hooks=false", "-o", str(output)]
    if model:
        command += ["--model", model]
    if effort:
        command += ["-c", f"model_reasoning_effort={json.dumps(effort)}"]
    if ephemeral:
        command += ["--ephemeral"]
    if neutral:
        command += ["-c", "project_doc_max_bytes=0"]
    if resume:
        command += ["resume", session_id(resume)]
    command += ["-"]
    env = dict(os.environ, LEX_CLAUDE_DISABLE="1", CODEX_HOME=str(codex_home()))
    for key in ("CODEX_THREAD_ID", "CLAUDECODE", "CLAUDE_CODE_CHILD_SESSION"):
        env.pop(key, None)
    output.unlink(missing_ok=True)
    result = bounded_run(command, input=prompt, env=env)
    if result.returncode:
        raise RuntimeError(f"Codex exited {result.returncode}: {result.stderr[-1500:]}")
    sid = None
    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started":
            sid = session_id(event["thread_id"])
        if event.get("type") in ("error", "turn.failed"):
            raise RuntimeError(f"Codex failed: {event}")
    if not output.is_file() or not output.read_text().strip():
        raise RuntimeError("Codex returned no answer")
    if not ephemeral and not sid:
        raise RuntimeError("Codex returned no persisted thread id")
    return sid


def verify(answer, phase, briefing=None):
    command = ["bash", str(Path(__file__).with_name("master.sh")), "verify",
               "--answer", str(answer), "--phase", phase, "--runtime", "codex"]
    if briefing:
        command += ["--briefing", str(briefing)]
    result = bounded_run(command, timeout=positive_env("LEX_CODEX_SUCCESSION_TIMEOUT", 180) + 10)
    try:
        verdict = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"invalid verifier response: {result.stderr[-500:]}")
    if result.returncode not in (0, 1) or type(verdict.get("pass")) is not bool:
        raise RuntimeError(f"{phase} verifier failed: {verdict}")
    return verdict


def run(args):
    if disabled():
        raise ValueError("succession disabled by LEX_CLAUDE_DISABLE or LEX_CLAUDE_HANDOFF_DISABLE")
    briefing = Path(args.briefing).resolve() if args.briefing else None
    brief = briefing.read_text() if briefing else None
    parent = os.environ.get("CODEX_THREAD_ID")
    previous = usage(transcript(parent)) if parent else {}
    model = previous.get("model")
    effort = previous.get("effort")
    root = state_dir()
    root.mkdir(parents=True, exist_ok=True)
    attempts = positive_env("LEX_CLAUDE_SUCCESSION_MAX", 3)
    watched_turns = int(os.environ.get("LEX_CLAUDE_WATCH_TURNS", "3"))
    if watched_turns < 0:
        raise ValueError("LEX_CLAUDE_WATCH_TURNS must be nonnegative")
    for attempt in range(1, attempts + 1):
        print(f">> Codex successor attempt {attempt}/{attempts}", file=sys.stderr, flush=True)
        try:
            with tempfile.TemporaryDirectory(prefix="lc-codex-") as tmp:
                output = Path(tmp) / "answer.txt"
                sid = codex_exec("In six lines, state your identity and specific non-negotiable rules "
                                 "from the loaded instructions. Do not edit files or start work.",
                                 output, model=model, effort=effort)
                # A thread.started event alone is not proof that it can be resumed.
                transcript(sid)
                verdict = verify(output, "identity")
                if not verdict["pass"]:
                    raise RuntimeError("identity gate: " + verdict["reason"])
                if brief is not None:
                    context = subprocess.run(["bash", str(Path(__file__).with_name("hook.sh"))],
                                             text=True, capture_output=True, check=True,
                                             env=dict(os.environ, LEX_CLAUDE_RUNTIME="codex"), timeout=30).stdout
                    codex_exec(context + "\n\nTake over this work. Briefing:\n" + brief +
                               "\nGive your concrete first move in six lines. Do not edit files or "
                               "execute that move yet. Wait for the handover kickoff.",
                               output, resume=sid, model=model, effort=effort)
                    verdict = verify(output, "project", briefing)
                    if not verdict["pass"]:
                        raise RuntimeError("project gate: " + verdict["reason"])
            break
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            print(f"   rejected: {error}", file=sys.stderr, flush=True)
    else:
        raise RuntimeError(f"SUCCESSION_FAILED after {attempts} attempts. Continue with native compaction.")

    generation = 1
    parent_state = root / f"{parent}.json"
    if parent and parent_state.exists():
        generation = json.loads(parent_state.read_text())["generation"]
    command = ["env", f"CODEX_HOME={codex_home()}", "codex", "-C", str(Path.cwd())]
    if model:
        command += ["--model", model]
    if effort:
        command += ["-c", f"model_reasoning_effort={json.dumps(effort)}"]
    sandbox = previous.get("sandbox_policy", {}).get("type")
    if sandbox in ("read-only", "workspace-write", "danger-full-access"):
        command += ["--sandbox", sandbox]
    if previous.get("approval_policy") in ("never", "on-request"):
        command += ["--ask-for-approval", previous["approval_policy"]]
    command += ["resume", sid]
    if brief is not None:
        command += ["Take over the briefed work now. Check the live state, then carry out your opening move."]
    saved = {"generation": generation + 1 if parent else 1, "parent": parent,
             "command": command, "briefing": brief, "watch_left": watched_turns if brief else 0}
    (root / f"{sid}.json").write_text(json.dumps(saved, indent=2) + "\n")
    if parent:
        import retirement
        retirement.register("codex", parent, sid)
    print(f"SUCCESSOR_OK {sid}")
    print("Resume with: " + shlex.join(command))
    if brief and watched_turns:
        print(f"Master watch armed for {watched_turns} turns; requires trusted Codex Stop hook.")
    if args.open:
        subprocess.run(["bash", str(Path(__file__).with_name("succeed.sh")), "open-codex", sid], check=True)


def wire():
    import re
    import tomllib

    home = codex_home()
    home.mkdir(parents=True, exist_ok=True)
    path = home / "hooks.json"
    original = path.read_text() if path.exists() else "{}"
    config = json.loads(original)
    command = shlex.join(["python3", str(Path(__file__).resolve()), "hook"])
    hooks = config.setdefault("hooks", {})
    for event in ("SessionStart", "PreToolUse", "UserPromptSubmit", "PostToolUse", "Stop"):
        groups = hooks.setdefault(event, [])
        # Remove only our handler; preserve other handlers in the same group.
        for group in groups:
            group["hooks"] = [item for item in group.get("hooks", [])
                              if item.get("command") != command]
        hooks[event] = [group for group in groups if group.get("hooks")]
        timeout = positive_env("LEX_CODEX_SUCCESSION_TIMEOUT", 180) + 15 if event == "Stop" else 10
        hooks[event].append({"hooks": [{"type": "command", "command": command, "timeout": timeout}]})
    rendered = json.dumps(config, indent=2) + "\n"
    if rendered != original:
        if path.exists():
            path.with_name(f"hooks.json.bak.{time.time_ns()}").write_text(original)
        with tempfile.NamedTemporaryFile(mode="w", dir=home, delete=False) as tmp:
            tmp.write(rendered)
        os.replace(tmp.name, path)
    print(f"codex: hooks wired at {path}. Review and trust them in /hooks.")

    path = home / "config.toml"
    original = path.read_text() if path.exists() else ""
    config = tomllib.loads(original)
    if "status_line" in config.get("tui", {}):
        print("codex: custom status line kept")
        return
    setting = 'status_line = ["model-with-reasoning", "context-used", "context-window-size", "used-tokens"]\n'
    match = re.search(r"^\[tui\][ \t]*(?:#.*)?$", original, re.MULTILINE)
    if match:
        rendered = original[:match.end()] + "\n" + setting + original[match.end():]
    elif "tui" not in config:
        rendered = original + "\n[tui]\n" + setting
    else:
        print("codex: existing tui config kept; use /statusline to select context-used and used-tokens")
        return
    tomllib.loads(rendered)
    if path.exists():
        path.with_name(f"config.toml.bak.{time.time_ns()}").write_text(original)
    with tempfile.NamedTemporaryFile(mode="w", dir=home, delete=False) as tmp:
        tmp.write(rendered)
    os.replace(tmp.name, path)
    print("codex: native context meter configured")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    tokens = sub.add_parser("tokens")
    tokens.add_argument("--session", default=os.environ.get("CODEX_THREAD_ID"))
    tokens.add_argument("--transcript", type=Path)
    tokens.add_argument("--json", action="store_true")
    sub.add_parser("hook")
    sub.add_parser("wire")
    runner = sub.add_parser("run")
    runner.add_argument("--briefing")
    runner.add_argument("--open", action="store_true")
    resume = sub.add_parser("resume")
    resume.add_argument("session")
    judge = sub.add_parser("judge")
    judge.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "hook":
            print(json.dumps(hook(json.load(sys.stdin))))
        elif args.command == "tokens":
            if not args.transcript and not args.session:
                raise ValueError("no CODEX_THREAD_ID; pass --session ID or --transcript PATH")
            data = usage(args.transcript or transcript(args.session))
            data["auto_compact_token_limit"] = compaction_limit(data)
            data["handoff_threshold"] = threshold(data)
            if args.json:
                print(json.dumps(data))
            else:
                value = lambda key: "unknown" if data[key] is None else str(data[key])
                print(f"codex context: {value('context_tokens')} / {value('model_context_window')} tokens; "
                      f"handoff: {value('handoff_threshold')}; compact: {value('auto_compact_token_limit')}; "
                      f"lifetime: {value('total_tokens')}")
            return 0 if data["context_tokens"] is not None else 1
        elif args.command == "wire":
            wire()
        elif args.command == "run":
            run(args)
        elif args.command == "judge":
            codex_exec(sys.stdin.read(), args.output, ephemeral=True, neutral=True,
                       model=os.environ.get("LEX_CODEX_MASTER_MODEL"))
        elif args.command == "resume":
            saved = json.loads((state_dir() / f"{session_id(args.session)}.json").read_text())
            os.environ.pop("CODEX_THREAD_ID", None)
            os.execvp(saved["command"][0], saved["command"])
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"codex: {error}", file=sys.stderr)
        if args.command == "hook":
            print("{}")
            return 0
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
