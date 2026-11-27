#!/usr/bin/env python3
"""Claims on a team repo's shared resources (team/TEAM.md, Claims), one holder at a time.

  lc claim take <resource> "<intent>" [--wait [minutes]] [--over <session-id>]
  lc claim release <resource>
  lc claim check <resource> [--held]
  lc claim status
  lc claim whoami                  this session's name and id, for a gate request's Lane: line
  lc claim name <session-id>       the name a live Claude session with that id has now

Resources: the keys of "resources" in the repo's .claude/team.json, read from the
current directory's checkout.

The holder is the Claude or Codex session this command runs under: the nearest
ancestor process named claude (its session id read from sessions/<pid>.json of
any ~/.claude* account) or codex (session codex-<pid>). Its pid and start time
are stored. A claim whose holder process is gone is stale: it stays claimed and
refuses everyone until a take names its session id with --over.

State lives in the git common dir of the current directory's repo (claims/), so
every worktree shares it. Every operation reads and writes under one kernel
lock, never held while sleeping. A claim file is replaced by rename, so a
reader never sees it half written.

Exit codes: 0 done, 1 usage or refusal by a non-holder, 3 held or stale.
"""

import fcntl
import glob
import json
import os
import subprocess
import sys
import time

POLL_SECONDS = 30
LOCK_SECONDS = 10
DEFAULT_WAIT_MINUTES = 60
CALL_SECONDS = 10


def die(msg, code=1):
    print(f"claim: {msg}", file=sys.stderr)
    sys.exit(code)


def run(*cmd, ok=(0,)):
    # Bounded, and fail closed: a hung or failing ps or git ends the operation, never a guess at a holder.
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=CALL_SECONDS)
    except subprocess.TimeoutExpired:
        die(f"{cmd[0]} did not answer within {CALL_SECONDS} s", 3)
    if r.returncode not in ok or r.stderr.strip():
        die(f"{' '.join(cmd)} failed ({r.returncode}): {r.stderr.strip()}", 3)
    return r.stdout.strip()


def started(pid):
    """Start time of a live pid, '' when it is gone. Same pid + same start = same process."""
    # ps exits 1 with no output for a pid that does not exist: that, and only that, means gone.
    return run("ps", "-o", "lstart=", "-p", str(pid), ok=(0, 1)) if pid else ""


def claims_dir():
    # CLAIM_DIR is for the tests only: they run on a scratch dir, never the real one.
    test = os.environ.get("CLAIM_DIR")
    if test:
        return test, True
    common = run("git", "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not common:
        die(f"no git repo at {os.getcwd()}")
    return os.path.join(common, "claims"), False


def resources(test):
    """The repo's resources, from .claude/team.json in this checkout; tests set CLAIM_RESOURCES."""
    if test and os.environ.get("CLAIM_RESOURCES"):
        return tuple(os.environ["CLAIM_RESOURCES"].split(","))
    top = run("git", "rev-parse", "--show-toplevel")
    try:
        with open(os.path.join(top, ".claude", "team.json")) as f:
            return tuple(json.load(f).get("resources", {}))
    except (OSError, ValueError) as e:
        die(f"no resources in {top}/.claude/team.json: {e}")


def sessions(test):
    """Claude session files of every ~/.claude* account; tests point CLAIM_SESSIONS at their own."""
    pattern = os.environ.get("CLAIM_SESSIONS") if test and os.environ.get("CLAIM_SESSIONS") else "~/.claude*/sessions/*.json"
    for f in glob.glob(os.path.expanduser(pattern)):
        try:
            with open(f) as fh:
                # Claude Code can rewrite a shorter file in place and leave bytes of the old one after it: read the
                # first object only.
                d, _ = json.JSONDecoder().raw_decode(fh.read())
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and d.get("sessionId"):
            yield d


def claude_session(pid, test=False):
    return next((d["sessionId"].upper() for d in sessions(test) if d.get("pid") == pid), "")


def live_name(session, test):
    """A moved session keeps its id and gets a new pid and name: the name of the live process with that id."""
    for d in sessions(test):
        pid = d.get("pid")
        if d["sessionId"].upper() == session.upper() and d.get("name") and isinstance(pid, int) and started(pid):
            return d["name"]
    return ""


def holder(test):
    """The agent process this command runs under, as stored in a claim."""
    if test and os.environ.get("CLAIM_HOLDER"):
        # Tests name a real long-lived process as holder: "<kind> <session> <pid>".
        kind, session, pid = os.environ["CLAIM_HOLDER"].split()
        return {"kind": kind, "session": session, "pid": int(pid), "start": started(pid)}
    pid = os.getppid()
    while pid > 1:
        ppid, _, comm = run("ps", "-o", "ppid=,comm=", "-p", str(pid)).partition(" ")
        name = os.path.basename(comm.strip())
        if name == "claude":
            session = claude_session(pid, test)
            if not session:
                die(f"claude pid {pid} has no sessions/{pid}.json in any ~/.claude* account")
            return {"kind": "claude", "session": session, "pid": pid, "start": started(pid)}
        if name == "codex":
            return {"kind": "codex", "session": f"codex-{pid}", "pid": pid, "start": started(pid)}
        if not ppid.strip():
            break
        pid = int(ppid)
    die("no Claude or Codex session above this command: run it from the session that does the work")


def alive(rec):
    return bool(rec["start"]) and started(rec["pid"]) == rec["start"]


def same(rec, me):
    if rec["session"] != me["session"]:
        return False
    # A Claude session moved to another account (lc move) keeps its verified id and gets a new pid.
    # A Codex id is only codex-<pid>: a reused pid is another process unless the start time matches.
    return rec["kind"] == "claude" == me["kind"] or (rec["pid"] == me["pid"] and rec["start"] == me["start"])


def describe(res, rec):
    state = "" if alive(rec) else " STALE: its process is gone; check the real state, then take it with --over " + rec["session"]
    return f"{res} held by {rec['session']} ({rec['kind']} pid {rec['pid']}) since {rec['since']}: {rec['intent']}{state}"


class Locked:
    """The kernel lock every operation runs under. Nonblocking tries until the deadline; never slept in."""

    def __init__(self, directory, deadline):
        self.path, self.deadline = os.path.join(directory, ".lock"), deadline

    def __enter__(self):
        self.fd = open(self.path, "a")
        while True:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except BlockingIOError:
                if time.monotonic() >= self.deadline:
                    self.fd.close()
                    die(f"lock {self.path} still busy at the deadline", 3)
                time.sleep(0.1)

    def __exit__(self, *exc):
        self.fd.close()


def read(directory, res):
    try:
        with open(os.path.join(directory, res)) as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def write(directory, res, rec):
    tmp = os.path.join(directory, f".{res}.{os.getpid()}")
    with open(tmp, "w") as f:
        json.dump(rec, f)
    os.replace(tmp, os.path.join(directory, res))


def take(directory, me, res, intent, wait_minutes, over):
    deadline = time.monotonic() + wait_minutes * 60
    told = False
    while True:
        with Locked(directory, max(deadline, time.monotonic() + LOCK_SECONDS)):
            rec = read(directory, res)
            if rec and same(rec, me):
                write(directory, res, {**rec, "kind": me["kind"], "pid": me["pid"], "start": me["start"], "intent": intent})
                print(f"already holding {res}, intent updated")
                return 0
            if rec is None or (over and not alive(rec) and over.upper() == rec["session"].upper()):
                write(directory, res, {**me, "intent": intent, "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
                print(f"took {res}")
                return 0
            line = describe(res, rec)
        remaining = deadline - time.monotonic()
        if not alive(rec) or remaining <= 0:
            print(line, file=sys.stderr)
            return 3
        if not told:
            print(f"{line}\nwaiting up to {wait_minutes} min, checking every {POLL_SECONDS} s", file=sys.stderr)
            told = True
        # The last sleep ends at the deadline, so the final check runs there.
        time.sleep(min(POLL_SECONDS, remaining))


def release(directory, me, res):
    with Locked(directory, time.monotonic() + LOCK_SECONDS):
        rec = read(directory, res)
        if rec is None:
            print(f"no claim on {res}")
            return 0
        if not same(rec, me):
            print(describe(res, rec) + "\nnot released: another session holds it", file=sys.stderr)
            return 1
        os.remove(os.path.join(directory, res))
        print(f"released {res}")
        return 0


def check(directory, me, res, held):
    with Locked(directory, time.monotonic() + LOCK_SECONDS):
        rec = read(directory, res)
        if rec and same(rec, me):
            if held:
                write(directory, res, {**rec, "kind": me["kind"], "pid": me["pid"], "start": me["start"]})
            return 0
        if rec is None and not held:
            return 0
        if rec:
            print(describe(res, rec), file=sys.stderr)
        if held:
            print(f'this session holds no claim on {res}: take it with lc claim take {res} "<intent>"', file=sys.stderr)
        return 3


def status(directory, known):
    shown = False
    # Every claim file, not only the known ones: a checkout behind main still shows a resource main added since.
    names = [f for f in sorted(os.listdir(directory)) if not f.startswith(".") and f not in known]
    for res in [*known, *names]:
        rec = read(directory, res)
        if rec:
            print(describe(res, rec))
            shown = True
    if not shown:
        print("no claims")
    return 0


def main(argv):
    if not argv or argv[0] not in ("take", "release", "check", "status", "whoami", "name"):
        die(__doc__.split("\n\n")[1])
    cmd, args = argv[0], argv[1:]
    directory, test = claims_dir()
    os.makedirs(directory, exist_ok=True)
    if cmd == "status":
        return status(directory, resources(test))
    if cmd == "whoami":
        me = holder(test)
        print(f"{(live_name(me['session'], test) if me['kind'] == 'claude' else '') or me['session']} {me['session']}")
        return 0
    if cmd == "name":
        if len(args) != 1:
            die("name <session-id>")
        name = live_name(args[0], test)
        if not name:
            print(f"no live Claude session with id {args[0]}", file=sys.stderr)
            return 3
        print(name)
        return 0
    known = resources(test)
    if not args or args[0] not in known:
        die(f"resource must be one of: {', '.join(known)}")
    res, rest = args[0], args[1:]
    me = holder(test)
    if cmd == "take":
        if not rest or rest[0].startswith("--"):
            die('take needs an intent: take <resource> "<intent>"')
        intent, rest = rest[0], rest[1:]
        wait, over = 0, ""
        while rest:
            if rest[0] == "--over" and len(rest) > 1:
                over, rest = rest[1], rest[2:]
            elif rest[0] == "--wait":
                wait, rest = DEFAULT_WAIT_MINUTES, rest[1:]
                if rest and rest[0].isdigit():
                    wait, rest = int(rest[0]), rest[1:]
                if wait <= 0:
                    die("--wait minutes must be positive")
            else:
                die(f"unknown argument {rest[0]}")
        return take(directory, me, res, intent, wait, over)
    if cmd == "release":
        return release(directory, me, res)
    if rest not in ([], ["--held"]):
        die("check <resource> [--held]")
    return check(directory, me, res, rest == ["--held"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
