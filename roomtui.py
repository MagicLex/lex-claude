#!/usr/bin/env python3
"""lc room: full-screen view of the room threads.

Left: a "+ new room" row for the repo at the current directory, then rooms,
newest first. Right: the selected thread, live. Bottom: a line that sends to
one lane or all of them. Sending, listing lanes and jumping go through room.sh
(room, lanes, go), so this file only reads the room files.
"""

import curses
import os
import re
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

ROOM_SH = Path(__file__).resolve().parent / "room.sh"
# Quick messages, one per line: a digit typed on an empty line fills one in.
QUICK = Path(__file__).resolve().parent / "room-quick.txt"
LEGACY = re.compile(r"^(\d\d:\d\d:\d\d) ([^:]+): (.*)$")
HELP = "up/down room  tab target  enter send  1-9 quick (empty line)  ^G jump  pgup/pgdn scroll  esc quit"
NEW = ""  # the "+ new room" row
SENT_ID = re.compile(r"\bid (\S+)")


def entries(path: Path) -> list[tuple[str, str, str]]:
    out = []
    if not path.exists():
        return out
    for line in path.read_text(errors="replace").splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 3:
            m = LEGACY.match(line)
            if not m:
                continue
            parts = list(m.groups())
        t, name, text = parts
        text = text[len(name):].lstrip(":, ") if text.startswith(name) else text
        out.append((t, name, text))
    return out


class Room:
    def __init__(self, d: Path, rid: str):
        self.id = rid
        self.lex = entries(d / f"{rid}.lex")
        self.replies = entries(d / f"{rid}.log")
        to = d / f"{rid}.to"
        self.to = [l for l in to.read_text().splitlines() if l.strip()] if to.exists() else []
        # Sorted on time only and stable: at the same second Lex comes first.
        self.thread = sorted(self.lex + self.replies, key=lambda e: e[0])

    def waiting(self) -> list[str]:
        if not self.lex:
            return []
        t, name, _ = self.lex[-1]
        # "SENDER > a, b"; rooms before names could hold spaces wrote "SENDER > a b".
        names = name.split(">", 1)[-1].strip()
        parts = names.split(", ")
        asked = parts if all(p in self.to for p in parts) else names.split()
        return [n for n in asked if not any(r[1] == n and r[0] >= t for r in self.replies)]

    def label(self) -> str:
        first = self.lex[0][2] if self.lex else "(no message)"
        return f"{self.id[9:11]}:{self.id[11:13]} {len(self.replies):>2}  {first}"


def room_ids(d: Path) -> list[str]:
    def touched(rid: str) -> float:
        return max((d / f"{rid}{ext}").stat().st_mtime for ext in (".log", ".lex") if (d / f"{rid}{ext}").exists())
    return sorted((p.stem for p in d.glob("*.log")), key=touched, reverse=True)[:50]


def run(*args: str, timeout: int = 60) -> list[str]:
    try:
        p = subprocess.run(["bash", str(ROOM_SH), *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return [f"room.sh {args[0]} gave no answer in {timeout}s (cmux busy?)"]
    lines = [l for l in (p.stdout + p.stderr).splitlines() if l.strip()]
    return lines or ["done" if p.returncode == 0 else f"failed ({p.returncode})"]


def fetch_lanes(box: dict) -> None:
    """Fill box["lanes"] off the UI thread: the lookup asks cmux, which can stall."""
    try:
        p = subprocess.run(["bash", str(ROOM_SH), "lanes"], capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        box["err"], box["lanes"] = "lane lookup gave no answer in 20s (cmux busy?)", []
        return
    if p.returncode != 0:
        box["err"] = (p.stderr.strip().splitlines() or [f"lane lookup failed ({p.returncode})"])[-1]
    box["lanes"] = [l for l in p.stdout.splitlines() if l.strip()] if p.returncode == 0 else []


def repo() -> str:
    p = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return Path(p.stdout.strip()).name if p.returncode == 0 else ""


def main(scr, d: Path, start: str | None):
    try:
        curses.curs_set(1)
    except curses.error:
        pass
    LEX = LANE = curses.A_BOLD
    if curses.has_colors():
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_YELLOW, -1)
        LEX, LANE = curses.color_pair(1) | curses.A_BOLD, curses.color_pair(2) | curses.A_BOLD
    SEL = curses.A_REVERSE
    scr.timeout(700)
    here = repo()
    lanes: dict | None = None  # live lanes of `here`, looked up when the new row is picked
    ids = room_ids(d)
    cur = start if start in ids else NEW
    target, buf, scroll, status = 0, "", 0, ""

    while True:
        # Rooms reorder as replies land: keep the selection on the same room.
        rows = [NEW] + room_ids(d)
        cur = cur if cur in rows else NEW
        sel = rows.index(cur)
        h, w = scr.getmaxyx()
        lw = min(34, w // 3)
        body = h - 5
        quick = [l.strip() for l in QUICK.read_text().splitlines() if l.strip()][:9] if QUICK.exists() else []
        tw = w - lw - 1
        lines: list[tuple[str, int]] = []
        if cur == NEW:
            if lanes is None and here:
                lanes = {}
                threading.Thread(target=fetch_lanes, args=(lanes,), daemon=True).start()
            found = (lanes or {}).get("lanes")
            targets = ["all"] + (found or [])
            if not here:
                lines = [("not in a git repo: run lc room inside one to start a room", 0)]
            else:
                shown = "looking..." if found is None else (", ".join(found) or (lanes or {}).get("err") or "none live")
                lines = [(f"new room in {here}", LEX), (f"lanes: {shown}", 0)]
            info = f"new room in {here}" if here else "no repo"
        else:
            room = Room(d, cur)
            targets = ["all"] + room.to
            for t, name, text in room.thread:
                lines.append((f"{name}  {t}", LEX if name.startswith("Lex") else LANE))
                lines += [(l, 0) for l in textwrap.wrap(text, max(tw - 2, 10)) or [""]]
                lines.append(("", 0))
            wait = room.waiting()
            info = f"{room.id}  " + (f"waiting on {' '.join(wait)}" if wait else "all answered")
        target %= len(targets)

        scr.erase()
        for i, rid in enumerate(rows[:body]):
            label = f"+ new room {here}" if rid == NEW else Room(d, rid).label()
            scr.addstr(i, 0, label[: lw - 1].ljust(lw - 1), SEL if i == sel else 0)
        for y in range(body):
            scr.addch(y, lw - 1, curses.ACS_VLINE)
        scroll = max(0, min(scroll, len(lines) - body))
        view = lines[max(0, len(lines) - body - scroll): len(lines) - scroll]
        for y, (l, a) in enumerate(view):
            scr.addstr(y, lw, l[: tw - 1] if a else ("  " + l)[: tw - 1], a)
        scr.hline(body, 0, curses.ACS_HLINE, w)
        scr.addstr(body + 1, 0, (status or info)[: w - 1], curses.A_DIM if not status else curses.A_BOLD)
        scr.addstr(h - 2, 0, "  ".join(f"{i} {q[:30]}" for i, q in enumerate(quick, 1))[: w - 1], curses.A_DIM)
        scr.addstr(h - 1, 0, HELP[: w - 1], curses.A_DIM)
        shown = (f"to {targets[target]} > " + buf)[-(w - 1):]
        scr.addstr(body + 2, 0, shown)
        scr.move(body + 2, min(len(shown), w - 2))
        scr.refresh()

        try:
            k = scr.get_wch()
        except curses.error:
            continue
        if k in ("\x1b", "\x03") or k == curses.KEY_EXIT:
            return
        status = ""
        if k in (curses.KEY_UP, curses.KEY_DOWN):
            cur = rows[max(0, sel - 1)] if k == curses.KEY_UP else rows[min(len(rows) - 1, sel + 1)]
            target, scroll = 0, 0
            if cur == NEW and lanes is not None and "lanes" in lanes:
                lanes = None
        elif k == curses.KEY_PPAGE:
            scroll += max(1, h - 6)
        elif k == curses.KEY_NPAGE:
            scroll = max(0, scroll - max(1, h - 6))
        elif k == "\t":
            target += 1
        elif k == curses.KEY_BTAB:
            target -= 1
        elif k in (curses.KEY_BACKSPACE, "\x7f", "\b"):
            buf = buf[:-1]
        elif k == "\x15":
            buf = ""
        elif k == "\x07":
            name = targets[target]
            status = "pick one lane with tab first" if name == "all" else run("go", name)[0]
        elif k in ("\n", "\r", curses.KEY_ENTER):
            if buf.strip() and (cur != NEW or here):
                scr.addstr(body + 1, 0, "sending...".ljust(w - 1)[: w - 1], curses.A_BOLD)
                scr.refresh()
                to = [] if targets[target] == "all" else ["--to", targets[target]]
                where = [] if cur == NEW else ["--in", cur]
                out = run("room", *where, *to, "--wait", "0", "--", buf.strip())
                status = out[0]
                if cur == NEW and (m := SENT_ID.search(status)) and (d / f"{m.group(1)}.log").exists():
                    cur = m.group(1)
                buf, scroll = "", 0
        elif not buf and isinstance(k, str) and k in "123456789" and int(k) <= len(quick):
            buf = quick[int(k) - 1]
        elif isinstance(k, str) and k.isprintable():
            buf += k


if __name__ == "__main__":
    d = Path(sys.argv[1])
    os.environ.setdefault("ESCDELAY", "25")
    try:
        curses.wrapper(main, d, sys.argv[2] if len(sys.argv) > 2 else None)
    except KeyboardInterrupt:
        pass
