#!/usr/bin/env python3
"""lc room: full-screen view of the room threads.

Left: rooms, newest first. Right: the selected thread, live. Bottom: a line
that sends a follow-up to one lane or all of them. Sending and jumping go
through room.sh (say --in, go), so this file only reads the room files.
"""

import curses
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

ROOM_SH = Path(__file__).resolve().parent / "room.sh"
LEGACY = re.compile(r"^(\d\d:\d\d:\d\d) ([^:]+): (.*)$")
HELP = "up/down room  tab target  enter send  ^G jump to lane  pgup/pgdn scroll  esc quit"


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
        self.to = to.read_text().split() if to.exists() else []
        # Sorted on time only and stable: at the same second Lex comes first.
        self.thread = sorted(self.lex + self.replies, key=lambda e: e[0])

    def waiting(self) -> list[str]:
        if not self.lex:
            return []
        t, name, _ = self.lex[-1]
        asked = name.split(">", 1)[-1].split()
        return [n for n in asked if not any(r[1] == n and r[0] >= t for r in self.replies)]

    def label(self) -> str:
        first = self.lex[0][2] if self.lex else "(no message)"
        return f"{self.id[9:11]}:{self.id[11:13]} {len(self.replies):>2}  {first}"


def room_ids(d: Path) -> list[str]:
    def touched(rid: str) -> float:
        return max((d / f"{rid}{ext}").stat().st_mtime for ext in (".log", ".lex") if (d / f"{rid}{ext}").exists())
    return sorted((p.stem for p in d.glob("*.log")), key=touched, reverse=True)[:50]


def run(*args: str) -> str:
    p = subprocess.run(["bash", str(ROOM_SH), *args], capture_output=True, text=True)
    lines = [l for l in (p.stdout + p.stderr).splitlines() if l.strip()]
    return lines[0] if lines else ("done" if p.returncode == 0 else f"failed ({p.returncode})")


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
    ids = room_ids(d)
    cur = start if start in ids else (ids[0] if ids else None)
    target, buf, scroll, status = 0, "", 0, ""

    while True:
        # Rooms reorder as replies land: keep the selection on the same room.
        ids = room_ids(d)
        cur = cur if cur in ids else (ids[0] if ids else None)
        sel = ids.index(cur) if cur else 0
        h, w = scr.getmaxyx()
        scr.erase()
        if not ids:
            scr.addstr(0, 0, "no rooms yet: lc say MESSAGE starts one. esc quits."[: w - 1])
        else:
            room = Room(d, ids[sel])
            targets = ["all"] + room.to
            target %= len(targets)
            lw = min(34, w // 3)
            body = h - 4

            for i, rid in enumerate(ids[:body]):
                scr.addstr(i, 0, Room(d, rid).label()[: lw - 1].ljust(lw - 1), SEL if i == sel else 0)
            for y in range(body):
                scr.addch(y, lw - 1, curses.ACS_VLINE)

            tw = w - lw - 1
            lines: list[tuple[str, int]] = []
            for t, name, text in room.thread:
                lines.append((f"{name}  {t}", LEX if name.startswith("Lex") else LANE))
                lines += [(l, 0) for l in textwrap.wrap(text, max(tw - 2, 10)) or [""]]
                lines.append(("", 0))
            scroll = max(0, min(scroll, len(lines) - body))
            view = lines[max(0, len(lines) - body - scroll): len(lines) - scroll]
            for y, (l, a) in enumerate(view):
                scr.addstr(y, lw, l[: tw - 1] if a else ("  " + l)[: tw - 1], a)

            scr.hline(body, 0, curses.ACS_HLINE, w)
            wait = room.waiting()
            info = f"{room.id}  " + (f"waiting on {' '.join(wait)}" if wait else "all answered")
            scr.addstr(body + 1, 0, (status or info)[: w - 1], curses.A_DIM if not status else curses.A_BOLD)
            scr.addstr(h - 1, 0, HELP[: w - 1], curses.A_DIM)
            prompt = f"to {targets[target]} > "
            shown = (prompt + buf)[-(w - 1):]
            scr.addstr(body + 2, 0, shown)
            scr.move(body + 2, min(len(shown), w - 2))
        scr.refresh()

        try:
            k = scr.get_wch()
        except curses.error:
            continue
        if k in ("\x1b", "\x03") or k == curses.KEY_EXIT:
            return
        if not ids:
            continue
        status = ""
        if k == curses.KEY_UP:
            cur, target, scroll = ids[max(0, sel - 1)], 0, 0
        elif k == curses.KEY_DOWN:
            cur, target, scroll = ids[min(len(ids) - 1, sel + 1)], 0, 0
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
            status = "pick one lane with tab first" if name == "all" else run("go", name)
        elif k in ("\n", "\r", curses.KEY_ENTER):
            if buf.strip():
                scr.addstr(body + 1, 0, "sending...".ljust(w - 1)[: w - 1], curses.A_BOLD)
                scr.refresh()
                to = [] if targets[target] == "all" else ["--to", targets[target]]
                status = run("say", "--in", ids[sel], *to, "--wait", "0", buf.strip())
                buf, scroll = "", 0
        elif isinstance(k, str) and k.isprintable():
            buf += k


if __name__ == "__main__":
    d = Path(sys.argv[1])
    os.environ.setdefault("ESCDELAY", "25")
    curses.wrapper(main, d, sys.argv[2] if len(sys.argv) > 2 else None)
