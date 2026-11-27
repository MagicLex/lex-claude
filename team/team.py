#!/usr/bin/env python3
"""Team mode for one repo (team/TEAM.md).

  lc team                        status: mode, red alert, config, roles
  lc team on|off                 switch the repo in the current directory
  lc team alert on|off           red alert: all work goes gate first (owner's order only)
  lc team role [gate|memory|lead|lane]   show or set this session's role
  lc team who <role>             live names of the sessions holding a role
  lc team config <key>           a value from .claude/team.json (gateDir expanded)
  lc team lane-prompt            the lane kickoff text, task on stdin
  lc team brief                  the subagent brief: TEAM.md's section plus the repo's lines

State lives in the repo's git common dir (lc-team/), so every worktree of a clone
shares it and nothing is tracked: on (the switch), alert, roles/<session id>.
The repo's specifics live in its tracked .claude/team.json:
  {"gateDir": "~/.x/gate", "firstReads": ["docs/PHILOSOPHY.md"],
   "resources": {"<name>": "<what it covers>"}, "subagentBrief": ["<line>"]}
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
TEAM_MD = os.path.join(HERE, "TEAM.md")
LANE_MD = os.path.join(HERE, "LANE.md")
MARKER = "<!-- The hook prepends everything below this comment"
ROLES = ("gate", "memory", "lead", "lane")
sys.path.insert(0, HERE)
import claim  # noqa: E402


def die(msg, code=1):
    print(f"team: {msg}", file=sys.stderr)
    sys.exit(code)


def git(*args, cwd=None):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10)
    return r.stdout.strip() if r.returncode == 0 else ""


def state_dir(cwd=None):
    common = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=cwd)
    return os.path.join(common, "lc-team") if common else ""


def is_on(cwd=None):
    d = state_dir(cwd)
    return bool(d) and os.path.exists(os.path.join(d, "on"))


def config(cwd=None):
    top = git("rev-parse", "--show-toplevel", cwd=cwd)
    try:
        with open(os.path.join(top, ".claude", "team.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def gate_dir(cwd=None):
    return os.path.expanduser(config(cwd).get("gateDir", ""))


def brief(cwd=None):
    text = open(TEAM_MD).read()
    body = text[text.index(MARKER):].split("\n", 1)[1].strip()
    lines = config(cwd).get("subagentBrief", [])
    return body + "".join(f"\n- {line}" for line in lines)


def lane_prompt(task, cwd=None):
    cfg = config(cwd)
    reads = cfg.get("firstReads") or ["the repo's CLAUDE.md"]
    return (open(LANE_MD).read()
            .replace("{team_md}", TEAM_MD)
            .replace("{first_reads}", ", ".join(reads))
            .replace("{gate_dir}", gate_dir(cwd) or "(none set in .claude/team.json)")
            .replace("{task}", task))


def me():
    rec = claim.holder(False)
    return rec["session"]


def who(role):
    d = os.path.join(state_dir(), "roles")
    names = []
    for sid in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        with open(os.path.join(d, sid)) as f:
            if f.read().strip() == role:
                name = claim.live_name(sid, False)
                if name:
                    names.append(name)
    return names


def status():
    d = state_dir()
    if not d:
        die("not in a git repo")
    top = git("rev-parse", "--show-toplevel")
    cfg_path = os.path.join(top, ".claude", "team.json")
    print(f"team: {'on' if is_on() else 'off'}")
    print(f"red alert: {'on' if os.path.exists(os.path.join(d, 'alert')) else 'off'}")
    print(f"config: {cfg_path if os.path.exists(cfg_path) else 'none (' + cfg_path + ')'}")
    print(f"protocol: {TEAM_MD}")
    print(f"gate dir: {gate_dir() or 'none'}")
    for role in ROLES[:3]:
        print(f"{role}: {', '.join(who(role)) or 'none'}")


def main(argv):
    cmd, args = (argv[0], argv[1:]) if argv else ("status", [])
    d = state_dir()
    if not d and cmd not in ("brief",):
        die("not in a git repo")
    if cmd == "status":
        return status()
    if cmd in ("on", "off"):
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "on")
        if cmd == "on":
            top = git("rev-parse", "--show-toplevel")
            if not os.path.exists(os.path.join(top, ".claude", "team.json")):
                die(f"no {top}/.claude/team.json: write and commit it first (gateDir, firstReads, resources, subagentBrief)")
            open(path, "w").close()
        elif os.path.exists(path):
            os.remove(path)
        print(f"team: {cmd} for {os.path.dirname(d)}. Sessions started from now on follow it.")
        return 0
    if cmd == "alert":
        if args not in (["on"], ["off"]):
            die("alert on|off")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "alert")
        if args[0] == "on":
            open(path, "w").close()
        elif os.path.exists(path):
            os.remove(path)
        print(f"red alert: {args[0]}")
        return 0
    if cmd == "role":
        sid = me()
        path = os.path.join(d, "roles", sid)
        if not args:
            print(open(path).read().strip() if os.path.exists(path) else "lane")
            return 0
        if args[0] not in ROLES:
            die(f"role must be one of: {', '.join(ROLES)}")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(args[0] + "\n")
        print(f"role: {args[0]}")
        return 0
    if cmd == "who":
        if len(args) != 1 or args[0] not in ROLES:
            die(f"who <{'|'.join(ROLES)}>")
        print("\n".join(who(args[0])))
        return 0
    if cmd == "config":
        if len(args) != 1:
            die("config <key>")
        value = gate_dir() if args[0] == "gateDir" else config().get(args[0], "")
        print(value if isinstance(value, str) else json.dumps(value))
        return 0
    if cmd == "lane-prompt":
        task = sys.stdin.read().strip() or "open TODO work"
        sys.stdout.write(lane_prompt(task))
        return 0
    if cmd == "brief":
        print(brief())
        return 0
    die(__doc__.split("\n\n")[1])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) or 0)
