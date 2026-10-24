#!/usr/bin/env python3
"""Local, server-rendered cmux session and evidence viewer. Python 3.9+."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import escape
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from hooks import ACTIVE_STATES, Hooks
import tracing
import roles as role_bindings
from trace_view import pane_trace, pane_usage, render_traces


HERE = Path(__file__).resolve().parent
SOURCE_LIMIT = 1024 * 1024
GATE_HEADER = re.compile(r"^(.+?):\s+(PASS|FIX)\b(.*)$", re.MULTILINE)
COMMIT_SUBJECT = re.compile(r"^(.+?)\s+([0-9a-f]{7,40})$")
KINDS = ("review", "docs", "handoff", "evidence", "blockers")
ROLES = ("Lead", "Worker", "Gate", "Review", "Docs")


def command(argv, timeout=5, env=None):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"{argv[0]}: {exc}") from exc
    if result.returncode:
        raise RuntimeError(f"{argv[0]}: {result.stderr.strip()[:500] or 'exit ' + str(result.returncode)}")
    return result.stdout.strip()


def cmux(*args, json_output=True):
    argv = ["cmux", "--id-format", "uuids"]
    if json_output:
        argv.append("--json")
    output = command([*argv, *args])
    return json.loads(output) if json_output else output


def timestamp(value):
    return datetime.fromtimestamp(value, timezone.utc).strftime("%d %b %Y, %H:%M:%S UTC") if value else "Unknown"


def read_config(path):
    if not path.exists():
        return {"projects": [], "sources": [], "targets": {}, "roles": {}, "links": [], "workspaces_root": None}
    config = json.loads(path.read_text())
    if not isinstance(config, dict) or not all(k in config for k in ("projects", "sources", "targets", "roles", "workspaces_root")):
        raise ValueError("Invalid control room configuration")
    config.setdefault("links", [])
    return config


def save_config(path, config):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as stream:
        os.chmod(temporary, 0o600)
        json.dump(config, stream, indent=2)
        stream.write("\n")
    temporary.replace(path)


def git_state(path):
    try:
        head = command(["git", "-C", path, "rev-parse", "--revs-only", "HEAD"])
        branch = command(["git", "-C", path, "branch", "--show-current"]) or "detached"
        dirty = bool(command(["git", "--no-optional-locks", "-C", path, "status", "--porcelain"]))
        if command(["git", "-C", path, "rev-parse", "--revs-only", "HEAD"]) != head:
            raise RuntimeError("Checkout changed during collection")
        return {"head": head, "branch": branch, "dirty": dirty, "error": ""}
    except RuntimeError as exc:
        return {"head": "", "branch": "", "dirty": None, "error": str(exc)}


def read_source(source):
    item = dict(source)
    try:
        with Path(source["path"]).open("rb") as stream:
            stat = os.fstat(stream.fileno())
            content = stream.read(SOURCE_LIMIT + 1)
            after = os.fstat(stream.fileno())
        if (stat.st_mtime_ns, stat.st_size) != (after.st_mtime_ns, after.st_size):
            raise ValueError("Source changed while reading; retrying")
        if len(content) > SOURCE_LIMIT:
            raise ValueError("Source exceeds 1 MiB; register a smaller document")
        item.update(text=content.decode("utf-8"), modified=stat.st_mtime, error="")
    except (OSError, UnicodeError, ValueError) as exc:
        item.update(text="", modified=None, error=str(exc))
    return item


def source_url(source):
    return "/source/" + sha256(source["path"].encode()).hexdigest()[:16]


def review_entries(text):
    matches = list(GATE_HEADER.finditer(text))
    entries = []
    for index, match in enumerate(matches):
        raw_subject = match[1].strip()
        parsed = COMMIT_SUBJECT.fullmatch(raw_subject)
        # A line can carry verdicts for several repositories. Keep it unbound.
        ambiguous = len(re.findall(r"\b[0-9a-f]{7,40}\b", raw_subject)) != 1 or bool(re.search(r":\s+(PASS|FIX)\b", match[3]))
        subject, commit = (parsed[1], parsed[2]) if parsed and not ambiguous else (raw_subject, "")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        entries.append({"subject": subject, "commit": commit, "verdict": match[2],
                        "mode": match[3].strip(), "text": text[match.start():end].strip(),
                        "line": text.count("\n", 0, match.start()) + 1})
    latest = {}
    for entry in reversed(entries):
        latest.setdefault(entry["subject"], entry)
    return list(latest.values())


def review_binding(entry, targets):
    target = targets.get(entry["subject"])
    if not entry["commit"] or not target:
        return "Unbound review", "No target commit verified"
    if target["error"]:
        return "Target unavailable", target["error"]
    if target["dirty"] or not target["head"].startswith(entry["commit"]):
        return "Revalidation needed", f"Current HEAD {target['head'][:12]}" + (" · uncommitted changes" if target["dirty"] else "")
    return "Commit matches", f"HEAD {target['head'][:12]} · recorded review only"


def project_for(cwd, projects):
    path = Path(cwd) if cwd else None
    candidates = [p for p in projects if path and (path == Path(p["path"]) or Path(p["path"]) in path.parents)]
    return max(candidates, key=lambda p: len(p["path"]))["name"] if candidates else "Unassigned"


def cmux_snapshot():
    tree = cmux("tree", "--all")
    rows, errors = [], []
    windows = tree["windows"]
    if len(windows) > 32:
        raise ValueError("More than 32 cmux windows; narrow the room before collecting")
    with ThreadPoolExecutor(max_workers=4) as pool:
        listings = [pool.submit(cmux, "workspace", "list", "--window", w["id"]) for w in windows]
        for window, future in zip(windows, listings):
            try:
                metadata = {w["id"]: w for w in future.result()["workspaces"]}
            except (RuntimeError, ValueError, KeyError) as exc:
                errors.append(f"cmux window {window['id']}: {exc}")
                continue
            for workspace in window["workspaces"]:
                meta = metadata.get(workspace["id"])
                if meta is None:
                    continue
                for pane in workspace["panes"]:
                    for surface in pane["surfaces"]:
                        if surface["type"] != "terminal":
                            continue
                        rows.append({"id": surface["id"], "window": window["id"], "workspace": workspace["id"],
                                     "title": surface.get("title") or workspace["title"], "workspace_title": workspace["title"],
                                     "cwd": meta.get("current_directory") or "", "tty": surface.get("tty") or "",
                                     "description": workspace.get("description") or "", "state": "Unreported",
                                     "detail": "", "runtime": "cmux"})
    return rows, errors


def collect(config):
    started = time.time()
    snapshot = {"collected_at": started, "sessions": [], "jobs": [], "sources": [], "projects": [], "targets": {}, "errors": []}
    with ThreadPoolExecutor(max_workers=4) as pool:
        cmux_future = pool.submit(cmux_snapshot)
        w9s_future = None
        if config["workspaces_root"]:
            env = dict(os.environ, WORKSPACES_DIR=config["workspaces_root"])
            w9s_path = config.get("w9s_path") or str(Path(config["workspaces_root"]) / "scripts" / "w9s")
            w9s_future = pool.submit(command, [sys.executable, w9s_path, "--snapshot-json", "--include-external"], 15, env)
        ps_future = pool.submit(command, ["ps", "-axo", "pid=,tty="])
        paths = {p["path"] for p in config["projects"]} | set(config["targets"].values())
        git_futures = {path: pool.submit(git_state, path) for path in paths}
        try:
            snapshot["sessions"], errors = cmux_future.result()
            snapshot["errors"].extend(errors)
        except (RuntimeError, ValueError, KeyError, TypeError) as exc:
            snapshot["errors"].append(f"cmux unavailable: {exc}")
        registry, ttys = [], {}
        try:
            if w9s_future:
                exported = json.loads(w9s_future.result())
                if exported["schema_version"] != 1:
                    raise ValueError("Unsupported w9s snapshot schema")
                registry, snapshot["jobs"] = exported["sessions"], exported["jobs"]
        except (RuntimeError, ValueError, KeyError, TypeError) as exc:
            snapshot["errors"].append(f"w9s unavailable: {exc}")
        try:
            ttys = dict(line.split() for line in ps_future.result().splitlines() if len(line.split()) == 2)
        except RuntimeError as exc:
            snapshot["errors"].append(f"Session matching unavailable: {exc}")
        git = {path: future.result() for path, future in git_futures.items()}
    matched = set()
    for row in snapshot["sessions"]:
        matches = [s for s in registry if s["kind"] == "interactive" and ttys.get(str(s["pid"]), "?") == row["tty"]]
        if len(matches) == 1:
            session = matches[0]
            row.update(state=session["state"], detail=session["detail"], runtime="Claude", session_id=session["session_id"],
                       cwd=session["cwd"], age_s=session["age_s"])
            matched.add(session["pid"])
        row["project"] = project_for(row["cwd"], config["projects"])
    for session in registry:
        if session["pid"] not in matched:
            snapshot["sessions"].append({"id": "", "title": session["name"], "workspace_title": "Outside cmux / unmatched",
                                         "cwd": session["cwd"], "state": session["state"], "detail": session["detail"],
                                         "runtime": "Claude", "role": "Unassigned", "description": session["kind"], "session_id": session["session_id"],
                                         "project": project_for(session["cwd"], config["projects"])})
    snapshot["projects"] = [dict(p, git=git[p["path"]]) for p in config["projects"]]
    snapshot["targets"] = {subject: git[path] for subject, path in config["targets"].items()}
    snapshot["sources"] = [read_source(source) for source in config["sources"]]
    snapshot["role_endpoints"], snapshot["role_resolutions"] = role_bindings.resolve(config, snapshot["sessions"], snapshot["sources"])
    snapshot["links"] = config["links"]
    snapshot["tracing"] = tracing.catalog(config, snapshot["sessions"])
    snapshot["completed_at"] = time.time()
    return snapshot


class Room:
    def __init__(self, config_path, interval):
        self.config_path, self.interval = config_path, interval
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.hooks = Hooks(self.wake)
        self.snapshot = {"collected_at": 0, "sessions": [], "projects": [], "sources": [], "jobs": [], "targets": {}, "errors": ["Collecting local sources"]}
        self.thread = threading.Thread(target=self.poll, name="room-collector")

    def poll(self):
        while not self.stop.is_set():
            self.wake.clear()
            try:
                current = collect(read_config(self.config_path))
            except Exception as exc:
                current = {"collected_at": time.time(), "sessions": [], "projects": [], "sources": [], "jobs": [], "targets": {}, "errors": [f"Collection failed: {exc}"]}
            with self.lock:
                self.snapshot = current
            if self.wake.wait(self.interval):
                self.stop.wait(1)

    def view(self):
        with self.lock:
            snapshot = dict(self.snapshot)
        if time.time() - snapshot["collected_at"] > max(45, self.interval * 3):
            snapshot.update(sessions=[], projects=[], sources=[], jobs=[], targets={}, links=[], role_endpoints={}, role_resolutions=[], tracing={"sessions": [], "error": "Trace snapshot expired."}, errors=["Snapshot expired. Waiting for a fresh collection."])
        snapshot["hooks"] = self.hooks.view()
        snapshot["sessions"] = [dict(row) for row in snapshot["sessions"]]
        for row in snapshot["sessions"]:
            event = snapshot["hooks"]["states"].get(row["id"])
            if event and snapshot["hooks"]["connected"] and 0 <= time.time() - event["at"] < 90:
                row.update(state=event["state"], detail=event["tool"], hook=event)
        return snapshot


def e(value):
    return escape(str(value), quote=True)


def badge(text, tone="neutral"):
    return f'<span class="badge {tone}">{e(text)}</span>'


def pane_button(session, token):
    if not session["id"]:
        return '<span class="muted">No matched pane</span>'
    return f'''<form method="post" action="/navigate" class="navigate"><input type="hidden" name="csrf" value="{e(token)}"><input type="hidden" name="surface" value="{e(session['id'])}"><button aria-label="Open {e(session['workspace_title'])}">Open pane ↗</button></form>'''


def work_notes(text):
    """Keep top-level status bullets verbatim; do not infer task completion from prose."""
    return [(number, line[2:].strip()) for number, line in enumerate(text.splitlines(), 1) if line.startswith("- ")]


def flow_links(snapshot, sessions):
    panes = {s["id"]: s for s in sessions if s["id"]}
    sources = {s["path"]: s for s in snapshot["sources"]}
    links, unavailable = [], 0
    endpoints = snapshot.get("role_endpoints", {})
    for recorded in snapshot.get("links", []):
        link = dict(recorded, **{key: endpoints.get(recorded[key], recorded[key]) for key in ("from", "to")})
        source = sources.get(link["source"])
        if link["from"] not in panes and link["to"] not in panes and (not source or source["project"] not in {s["project"] for s in sessions}):
            continue
        lines = source["text"].splitlines() if source and not source["error"] else []
        number = link["line"]
        if (link["from"] not in panes or link["to"] not in panes or link["from"] == link["to"] or not source
                or panes[link["from"]]["project"] != source["project"]
                or panes[link["to"]]["project"] != source["project"]
                or not 0 < number <= len(lines) or lines[number - 1] != link["quote"]):
            unavailable += 1
            continue
        links.append(dict(link, href=source_url(source) + f"#L{number}"))
    return links, unavailable


def role_evidence(snapshot, session):
    body = '<div class="role-evidence"><h3>Role evidence</h3>'
    sources = {s["path"]: s for s in snapshot["sources"]}
    for binding in session.get("role_evidence", []):
        body += f'<p>{e(" / ".join(binding["roles"]))} · {e("Session " + binding["session_id"] if binding.get("session_id") else "Surface pointer" if binding["evidence"] else "Pinned surface")}</p>'
        body += f'<p class="quiet">Binding {e(binding["anchor"])} → {e(binding["surface"])}</p>'
        for item in binding["evidence"]:
            source = sources.get(item["path"])
            label = f'{item["path"]}:{item["line"]}'
            body += '<div class="route-source">'
            body += f'<a href="{e(source_url(source))}#L{item["line"]}">{e(label)}</a>' if source else f'<small>{e(label)}</small>'
            body += f'<span>{e(item["quote"])}</span></div>'
    return body + '</div>'


def render_flow(snapshot, sessions, token, selected=""):
    links, unavailable = flow_links(snapshot, sessions)
    hooks = snapshot.get("hooks", {"connected": False, "events": []})
    body = '<div class="setup" aria-label="Project setup">'
    for role in ("Lead", "Gate", "Review", "Docs"):
        assigned = [s for s in sessions if role in s.get("roles", [s["role"]])]
        names = ", ".join(s["workspace_title"] for s in assigned)
        label = "Gate / Invariants" if role == "Gate" else role
        body += f'<div class="setup-role {"assigned" if assigned else "missing"}"><b>{label}</b><span title="{e(names)}">{e(names or "Not assigned")}</span></div>'
    body += '</div><div class="flow-toolbar"><span class="flow-legend">Arrows: recorded routes</span><div class="zoom-controls" aria-label="Graph zoom"><button type="button" data-zoom="out" aria-label="Zoom out">−</button><button type="button" data-zoom="fit">Fit</button><button type="button" data-zoom="in" aria-label="Zoom in">+</button></div></div>'
    for binding in snapshot.get("role_resolutions", []):
        if binding["error"] and (not selected or binding["project"] == selected):
            body += f'<p class="quiet">{e(" / ".join(binding["roles"]))} unavailable: {e(binding["error"])}</p>'
    if unavailable:
        body += f'<p class="quiet">{unavailable} recorded links unavailable. Check source evidence and role bindings.</p>'
    linked = {link[key] for link in links for key in ("from", "to")}
    panes = [s for s in sessions if s["id"] and (s["role"] != "Unassigned" or s["id"] in linked)]
    other_panes = [s for s in sessions if s["id"] and s not in panes]
    columns = [[], [], [], []]
    for session in sorted(panes, key=lambda s: (s["project"], s["workspace_title"], s["id"])):
        roles = session.get("roles", [session["role"]])
        column = 0 if "Lead" in roles else 2 if set(roles) & {"Gate", "Review"} else 3 if "Docs" in roles else 1
        columns[column].append(session)
    height = max(450, max(len(column) for column in columns) * 106 + 90)
    positions = {}
    for index, column in enumerate(columns):
        for row, session in enumerate(column):
            positions[session["id"]] = (32 + index * 290, 64 + row * 106 + (height - 90 - len(column) * 106) / 2)
    body += f'<div class="flow-layout"><div class="flow-canvas"><svg class="flow-graph" viewBox="0 0 1190 {height}" data-fit="0 0 1190 {height}" tabindex="0" aria-label="Project agent graph. Use zoom controls or drag the background."><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z"/></marker></defs>'
    for index, label in enumerate(("LEAD", "AGENTS", "GATES / REVIEW", "DOCS")):
        body += f'<text class="flow-column" x="{32 + index * 290}" y="32">{label}</text>'
    for link in links:
        x1, y1 = positions[link["from"]]
        x2, y2 = positions[link["to"]]
        y1, y2 = y1 + 44, y2 + 44
        start, end = x1 + 244, x2 - 5
        bend = max(30, abs(end - start) / 2)
        if x1 - x2 > 290:
            path = f"M {x1 + 122} {y1 - 44} V 48 H {x2 + 122} V {y2 - 49}"
        elif x2 < x1:
            start, end = x1 - 5, x2 + 244
            bend = abs(end - start) / 2
            path = f"M {start} {y1} C {start - bend} {y1}, {end + bend} {y2}, {end} {y2}"
        else:
            path = f"M {start} {y1} C {start + bend} {y1}, {end - bend} {y2}, {end} {y2}"
        body += f'<a href="{e(link["href"])}" aria-label="{e(link["label"])} source"><path class="flow-edge" data-from="{e(link["from"])}" data-to="{e(link["to"])}" d="{path}" marker-end="url(#arrow)"><title>{e(link["label"])} · {e(link["quote"])}</title></path></a>'
    for session in panes:
        sid = session["id"]
        x, y = positions[sid]
        active = session["state"] in ACTIVE_STATES
        waiting = session["state"] in ("needs input", "suspended")
        lane = next((link["quote"].partition(": ")[2] for link in links if link["to"] == sid and link["label"] == "Coordinates"), "")
        trace = pane_trace(snapshot, session)
        value = trace["metrics"] if trace else None
        caption = f'{value["outputTokens"]:,} out · {value["cacheCreationTokens"]:,} cache write' if value else session['detail'] or lane or ('Recorded route' if sid in linked else 'No recorded links')
        body += f'''<foreignObject x="{x}" y="{y}" width="244" height="92"><a xmlns="http://www.w3.org/1999/xhtml" class="flow-node {"is-running" if active else ""} {"is-waiting" if waiting else ""}" data-node="{e(sid)}" data-state="{e(session['state'])}" href="#flow-{e(sid)}"><span class="node-role">{e(session['role'])} · {e(session['runtime'])}</span><strong title="{e(session['workspace_title'])}">{e(session['workspace_title'])}</strong><span class="node-state"><i></i>{e(session['state'])}</span><small title="{e(lane)}">{e(caption)}</small></a></foreignObject>'''
    if not panes:
        body += '<text class="flow-empty" x="40" y="110">No panes reported for this project.</text>'
    body += '</svg></div><aside class="flow-inspector"><div class="flow-help"><h2>Inspect</h2><p>Select an agent to see its work and connected routes.</p></div>'
    for session in panes:
        sid = session["id"]
        related = [link for link in links if sid in (link["from"], link["to"])]
        anchors = " ".join(r["anchor"] for r in session.get("role_evidence", []))
        body += f'<article class="flow-detail" id="flow-{e(sid)}" data-bindings="{e(anchors)}"><span class="eyebrow">{e(session["role"])}</span><h2>{e(session["workspace_title"])}</h2><p>{e(session["project"])} · {e(session["runtime"])}</p>{badge(session["state"])}<p>{e(session["detail"])}</p>{pane_button(session, token)}{pane_usage(snapshot, session)}{role_evidence(snapshot, session)}<h3>Recorded routes</h3>'
        for link in related:
            other = next(s for s in panes if s["id"] == (link["to"] if sid == link["from"] else link["from"]))
            body += f'<a class="route-source" href="{e(link["href"])}"><b>{e(link["label"])} · {e(other["workspace_title"])}</b><span>{e(link["quote"])}</span><small>Source L{link["line"]} ↗</small></a>'
        if not related:
            body += '<p>No recorded links.</p>'
        body += '</article>'
    ids = {s["id"]: s["workspace_title"] for s in panes}
    events = [event for event in hooks["events"] if event["surface"] in ids][-8:]
    body += f'<div class="flow-activity"><h3>Activity <span class="hook-status {"connected" if hooks["connected"] else ""}">{"Hooks live" if hooks["connected"] else "Hooks offline"}</span></h3><ol>'
    for event in reversed(events):
        body += f'<li data-event="{e(event["id"])}"><time>{e(datetime.fromtimestamp(event["at"]).strftime("%H:%M:%S"))}</time><b>{e(ids[event["surface"]])}</b><span>{e(event["name"])}{e(" · " + event["tool"] if event["tool"] else "")}</span></li>'
    body += '</ol>' + ('<p>No hook events observed for these panes yet.</p>' if not events else '') + '</div></aside></div>'
    if other_panes:
        body += f'<details class="other-panes"><summary>Other panes ({len(other_panes)})</summary><p>No role or route recorded in this setup.</p>'
        for session in other_panes:
            body += f'<div class="other-pane"><div><b>{e(session["workspace_title"])}</b><p>{e(session["state"])} · {e(session["description"])}</p></div>{pane_button(session, token)}</div>'
        body += '</details>'
    return body


def shell(body, selected="", page="overview"):
    query = urlencode({"project": selected}) if selected else ""
    nav = "".join(f'<a class="{"active" if page == slug else ""}" href="/?{urlencode({"project": selected, "view": slug})}">{label}</a>'
                  for slug, label in (("overview", "Work"), ("flow", "Flow"), ("traces", "Traces"), ("sessions", "Sessions"), ("reviews", "Reviews"), ("sources", "Sources")))
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Control room · cmux</title><link rel="stylesheet" href="/style.css"><script src="/room.js" defer></script></head>
<body class="page-{e(page)}"><aside class="rail"><a class="brand" href="/?{query}"><img src="/wordmark.svg" alt="Control room"></a>
<nav>{nav}</nav><div class="rail-foot"><span class="dot"></span> LOCAL / CMUX</div></aside>
<main>{body}</main><div id="notice" role="status" aria-live="polite"></div></body></html>'''


def render(snapshot, token, query, trace=None):
    selected = query.get("project", [""])[0]
    page = query.get("view", ["overview"])[0]
    if page not in ("overview", "flow", "traces", "sessions", "reviews", "sources"):
        page = "overview"
    sessions = [s for s in snapshot["sessions"] if not selected or s["project"] == selected]
    sources = [(i, s) for i, s in enumerate(snapshot["sources"]) if not selected or s["project"] == selected]
    reviews = [(i, source, entry) for i, source in sources if source["kind"] == "review" for entry in review_entries(source["text"])]
    attention = [s for s in sessions if s["state"] in ("needs input", "suspended")]
    options = '<option value="">All projects</option>' + ''.join(f'<option value="{e(p["name"])}" {"selected" if p["name"] == selected else ""}>{e(p["name"])}</option>' for p in snapshot["projects"])
    if selected and not any(p["name"] == selected for p in snapshot["projects"]):
        options += f'<option value="{e(selected)}" selected>{e(selected)}</option>'
    refresh_url = "/?" + urlencode({k: v[0] for k, v in query.items() if k in ("project", "view", "trace", "agent", "tool_page")})
    title = {"overview": selected or "All projects", "flow": selected or "Flow", "traces": "Claude traces", "sessions": "Sessions", "reviews": "Reviews", "sources": "Sources"}[page]
    body = f'''<header><h1>{e(title)}</h1><div class="header-actions">
<form method="get"><input type="hidden" name="view" value="{e(page)}"><label for="project" class="sr-only">Project</label><select id="project" name="project">{options}</select><button id="filter-button">Filter</button></form>
<a id="refresh" href="{e(refresh_url)}">Refresh ↻</a></div></header>
<div class="snapshot">Updated <time>{e(timestamp(snapshot['collected_at']))}</time></div>'''
    body += ''.join(f'<div class="alert">{e(error)}</div>' for error in snapshot["errors"])
    if page == "flow":
        body += render_flow(snapshot, sessions, token, selected)
    elif page == "traces":
        body += render_traces(snapshot, selected, query, trace)
    else:
        body += '<div class="counts">' + ''.join(f'<a href="/?{urlencode({"project": selected, "view": view})}"><b>{count}</b> {label}</a>' for count, label, view in ((len(sessions), "sessions", "sessions"), (len(reviews), "reviews", "reviews"), (len(sources), "sources", "sources"))) + '</div>'
    if page == "overview":
        body += '<section><div class="section-heading"><h2>Needs input</h2></div>'
        for session in attention:
            body += f'<div class="attention-row"><div><b>{e(session["workspace_title"])}</b><p>{e(session["detail"] or session["state"])}</p></div>{pane_button(session, token)}</div>'
        source_errors = [(i, s) for i, s in sources if s["error"]]
        for index, source in source_errors:
            body += f'<div class="alert"><a href="{source_url(source)}">{e(source["label"])}</a>: {e(source["error"])}</div>'
        if not attention and not source_errors:
            body += '<p class="quiet">No input requests reported.</p>'
        body += '</section>'
        rechecks = [(i, s, r) for i, s, r in reviews if review_binding(r, snapshot["targets"])[0] in ("Revalidation needed", "Target unavailable")]
        if rechecks:
            body += '<section><div class="section-heading"><h2>Review out of date</h2></div>'
            for index, source, entry in rechecks:
                status, detail = review_binding(entry, snapshot["targets"])
                body += f'<a class="attention-row" href="/?{urlencode({"project": selected, "view": "reviews"})}#{e("review-" + str(index) + "-" + str(entry["line"]))}"><div><b>{e(entry["subject"])}</b><p>{e(detail)}</p></div>{badge(status, "warn")}</a>'
            body += '</section>'
        states = [(i, s) for i, s in sources if s["kind"] == "blockers"]
        for index, source in states:
            body += f'<section><div class="section-heading"><h2>{e(source["label"])}</h2><a class="muted" href="{source_url(source)}">{e(timestamp(source["modified"]))} ↗</a></div><div class="work-list">'
            for number, note in work_notes(source["text"]):
                title, separator, description = note.partition(":")
                if not separator:
                    title, description = "", note
                body += f'<a class="work-row" href="{source_url(source)}#L{number}"><b>{e(title)}</b><span>{e(description.strip())}</span><span class="source-line">L{number} ↗</span></a>'
            body += '</div></section>'
        if not states:
            body += '<p class="quiet">No work state registered.</p>'
        leads = [s for s in sessions if set(s.get("roles", [s["role"]])) & {"Lead", "Review"}]
        if leads:
            body += '<section><div class="section-heading"><h2>Team</h2></div><div class="team-links">'
            for session in leads:
                body += f'<div>{badge(session["role"])}<b>{e(session["workspace_title"])}</b>{pane_button(session, token)}</div>'
            body += '</div></section>'
    if page == "sessions":
        body += '<section><div class="section-heading"><h2>Sessions</h2></div><div class="sessions">'
        for s in sessions:
            tone = "warn" if s["state"] in ("needs input", "suspended") else "neutral"
            action = pane_button(s, token)
            body += f'''<article class="session"><div class="session-top">{badge(s['role'])}{badge(s['state'], tone)}</div><h3>{e(s['workspace_title'])}</h3><p class="terminal-title">{e(s['title'])}</p><p class="detail">{e(s['detail'])}</p>
<div class="session-meta">{e(s['runtime'])} · {e(s['project'])}<br><span title="{e(s['cwd'])}">{e(s['cwd'])}</span></div>
<div class="session-bottom"><small>{e(s['description'])}</small>{action}</div></article>'''
        body += '</div>' + ('<p class="empty">No sessions reported for this selection.</p>' if not sessions else '') + '</section>'
    if page == "reviews":
        body += '<section><div class="section-heading"><h2>Reviews</h2><span>Saved verdicts. Deployment unverified.</span></div>'
        if not reviews:
            body += '<p class="empty">No verdicts parsed. Check Sources.</p>'
        for index, source, entry in reviews:
            status, detail = review_binding(entry, snapshot["targets"])
            body += f'''<details class="review" id="review-{index}-{entry['line']}"><summary><span>{badge(entry['verdict'], 'warn' if entry['verdict'] == 'FIX' else 'pass')}<b>{e(entry['subject'])}</b><code>{e(entry['commit'] or 'no single commit')}</code></span><span class="binding">{e(status)} <span class="chevron">⌄</span></span></summary>
<div class="review-body"><div class="provenance">{e(detail)}<br>{e(entry['mode'])}<br>File: {e(timestamp(source['modified']))} · Verdict time unknown<br><a href="{source_url(source)}">{e(source['label'])}:{entry['line']} ↗</a></div><pre>{e(entry['text'])}</pre></div></details>'''
        body += '</section>'
    if page == "sources":
        body += '<section><div class="section-heading"><h2>Sources</h2></div><div class="sources">'
        for index, source in sources:
            body += f'''<a class="source" href="{source_url(source)}"><span class="eyebrow">{e(source['kind'])} / {e(source['project'])}</span><h3>{e(source['label'])} ↗</h3><p>{e(source['error'] or timestamp(source['modified']))}</p><small>{e(source['path'])}</small></a>'''
        body += '</div>' + ('<p class="empty">No sources registered.</p>' if not sources else '') + '</section>'
    if page == "sources":
        body += '<section><div class="section-heading"><h2>Repositories</h2></div><div class="projects">'
        for project in snapshot["projects"]:
            if selected and selected != project["name"]:
                continue
            git = project["git"]
            body += f'<div><h3>{e(project["name"])}</h3><p>{e(git["error"] or git["branch"])}</p><code>{e(git["head"][:12] or ("No commits" if not git["error"] else ""))}</code> {badge("Uncommitted changes" if git["dirty"] else "Clean" if not git["error"] else "Unavailable")}<small>{e(project["path"])}</small></div>'
        body += '</div></section>'
        # Jobs belong to w9s workspace names, not to arbitrary project registrations.
        if snapshot["jobs"] and not selected:
            body += '<section><div class="section-heading"><h2>w9s jobs</h2></div>'
            for job in snapshot["jobs"]:
                body += f'<p>{e(job["ws"])} / {e(job["action"])} {e(job["target"])} {badge(job["status"])} <small>{e(timestamp(job["started_s"]))}</small></p>'
            body += '</section>'
    body += '<footer>cmux / w9s</footer>'
    return shell(body, selected, page)


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, fmt, *args):
        if args and str(args[1] if len(args) > 1 else "").startswith("5"):
            super().log_message(fmt, *args)

    def trusted(self):
        return self.headers.get("Host") == self.server.authority

    def respond(self, status, body, content_type="text/html; charset=utf-8"):
        content = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'; img-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        if not self.trusted():
            return self.respond(403, "Invalid host")
        url = urlsplit(self.path)
        snapshot = self.server.room.view()
        if url.path in ("/style.css", "/room.js", "/wordmark.svg"):
            name = url.path[1:]
            content_type = {"style.css": "text/css", "room.js": "text/javascript", "wordmark.svg": "image/svg+xml"}[name]
            return self.respond(200, (HERE / name).read_text(), content_type)
        if url.path == "/health":
            return self.respond(200, json.dumps({"collected_at": snapshot["collected_at"], "errors": snapshot["errors"]}), "application/json")
        if url.path == "/":
            query = parse_qs(url.query)
            trace = None
            if query.get("view") == ["traces"] and query.get("trace"):
                selected = query.get("project", [""])[0]
                row = next((r for r in snapshot.get("tracing", {}).get("sessions", [])
                            if r["id"] == query["trace"][0] and (not selected or r["project"] == selected)), None)
                if row:
                    try:
                        trace = tracing.detail(read_config(self.server.room.config_path), row)
                    except (OSError, ValueError, KeyError, TypeError) as exc:
                        trace = {"error": f"Trace unavailable: {exc}"}
            return self.respond(200, render(snapshot, self.server.room.token, query, trace))
        if re.fullmatch(r"/source/[a-f0-9]{16}", url.path):
            source = next((s for s in snapshot["sources"] if source_url(s) == url.path), None)
            if source:
                lines = "\n".join(f'<span id="L{number}" data-line="{number}">{e(line)}</span>' for number, line in enumerate((source["error"] or source["text"]).splitlines(), 1))
                body = f'<a class="back" href="/?{urlencode({"project": source["project"]})}">← Back</a><h1>{e(source["label"])}</h1><p>{e(source["path"])}</p><p>File modified {e(timestamp(source["modified"]))}</p><pre class="document">{lines}</pre>'
                return self.respond(200, shell(body, source["project"], "sources"))
        self.respond(404, "Not found")

    def do_POST(self):
        if not self.trusted() or self.headers.get("Origin") != f"http://{self.server.authority}":
            return self.respond(403, "Same-origin request required")
        if self.path != "/navigate":
            return self.respond(404, "Not found")
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096 or self.headers.get("Content-Type", "").split(";")[0] != "application/x-www-form-urlencoded":
                return self.respond(400, "Invalid form")
            form = parse_qs(self.rfile.read(length).decode("utf-8"), max_num_fields=4)
            if not secrets.compare_digest(form.get("csrf", [""])[0], self.server.room.token):
                return self.respond(403, "Invalid form token")
            surface = form.get("surface", [""])[0]
            if not surface or not any(row["id"] == surface for row in self.server.room.view()["sessions"]):
                return self.respond(409, "Pane no longer available. Refresh the room.")
            rows, _ = cmux_snapshot()
            row = next((r for r in rows if r["id"] == surface), None)
            if row is None:
                return self.respond(409, "Pane closed. Refresh the room.")
            cmux("select-workspace", "--workspace", row["workspace"], "--window", row["window"], json_output=False)
            cmux("focus-panel", "--panel", row["id"], "--workspace", row["workspace"], "--window", row["window"], json_output=False)
            if self.headers.get("Accept") == "application/json":
                return self.respond(200, json.dumps({"opened": surface}), "application/json")
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
        except (ValueError, UnicodeError) as exc:
            self.respond(400, e(exc))
        except (RuntimeError, KeyError, TypeError) as exc:
            self.respond(502, e(exc))


def serve(config_path, port, interval):
    room = Room(config_path, interval)
    with HTTPServer(("127.0.0.1", port), Handler) as server:
        server.room = room
        server.authority = f"127.0.0.1:{server.server_port}"
        server.timeout = 0.5
        def stop(signum, frame):
            room.stop.set()
            room.wake.set()
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        room.thread.start()
        room.hooks.thread.start()
        print(f"Control room: http://{server.authority}", flush=True)
        try:
            while not room.stop.is_set():
                server.handle_request()
        finally:
            room.stop.set()
            room.wake.set()
            room.hooks.close()
            room.thread.join()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=HERE / ".control-room" / "config.json")
    sub = parser.add_subparsers(dest="action", required=True)
    server = sub.add_parser("serve")
    server.add_argument("--port", type=int, default=0, help="0 chooses a free loopback port")
    server.add_argument("--interval", type=int, default=15)
    sub.add_parser("snapshot")
    project = sub.add_parser("add-project")
    project.add_argument("name")
    project.add_argument("path", type=Path)
    source = sub.add_parser("add-source")
    source.add_argument("project")
    source.add_argument("kind", choices=KINDS)
    source.add_argument("path", type=Path)
    source.add_argument("--label")
    target = sub.add_parser("bind-target")
    target.add_argument("subject")
    target.add_argument("path", type=Path)
    role = sub.add_parser("set-role")
    role.add_argument("surface", help="Stable cmux surface UUID")
    role.add_argument("role", nargs="+", choices=ROLES)
    role.add_argument("--project", help="Registered project for this binding")
    follow = role.add_mutually_exclusive_group()
    follow.add_argument("--session", help="Follow this session UUID through recorded successors")
    follow.add_argument("--pointer", type=Path, help="Registered source containing the current surface UUID")
    role.add_argument("--lineage-dir", type=Path, help="Directory of session generation and predecessor records")
    link = sub.add_parser("link", help="Record an agent route backed by a registered source line")
    link.add_argument("sender", help="Source cmux surface UUID")
    link.add_argument("receiver", help="Destination cmux surface UUID")
    link.add_argument("--label", required=True)
    link.add_argument("--source", type=Path, required=True)
    link.add_argument("--line", type=int, required=True)
    unlink = sub.add_parser("unlink")
    unlink.add_argument("sender")
    unlink.add_argument("receiver")
    root = sub.add_parser("set-workspaces-root")
    root.add_argument("path", type=Path)
    root.add_argument("--w9s", type=Path, help="External w9s script; defaults to <path>/scripts/w9s")
    trace_reader = sub.add_parser("set-tracing-url")
    trace_reader.add_argument("url", help="Local claude-devtools HTTP URL")
    args = parser.parse_args()
    try:
        config = read_config(args.config)
        if args.action == "serve":
            if not 1 <= args.interval <= 60:
                parser.error("interval must be 1..60 seconds")
            serve(args.config, args.port, args.interval)
            return
        if args.action == "snapshot":
            print(json.dumps(collect(config), indent=2))
            return
        if hasattr(args, "path"):
            args.path = args.path.expanduser().resolve(strict=True)
        if args.action == "add-project":
            if not args.path.is_dir():
                parser.error("project path must be a directory")
            config["projects"] = [p for p in config["projects"] if p["name"] != args.name] + [{"name": args.name, "path": str(args.path)}]
        elif args.action == "add-source":
            if args.project not in [p["name"] for p in config["projects"]]:
                parser.error("register the project first")
            if not args.path.is_file():
                parser.error("source must be a file")
            item = {"project": args.project, "kind": args.kind, "path": str(args.path), "label": args.label or args.path.name}
            config["sources"] = [s for s in config["sources"] if s["path"] != str(args.path)] + [item]
        elif args.action == "bind-target":
            if git_state(str(args.path))["error"]:
                parser.error("target must be a readable git checkout")
            config["targets"][args.subject] = str(args.path)
        elif args.action == "set-role":
            if not role_bindings.UUID.fullmatch(args.surface):
                parser.error("use a cmux surface UUID")
            binding = {}
            if args.session or args.pointer or args.project or args.lineage_dir:
                if args.project not in [p["name"] for p in config["projects"]]:
                    parser.error("provide a registered --project for the binding")
                binding["project"] = args.project
            if args.session:
                if not role_bindings.UUID.fullmatch(args.session):
                    parser.error("use a session UUID")
                binding["session_id"] = args.session.upper()
            if args.lineage_dir:
                if not args.session:
                    parser.error("--lineage-dir requires --session")
                directory = args.lineage_dir.expanduser().resolve(strict=True)
                role_bindings.lineage_records(directory)
                binding["lineage_dir"] = str(directory)
            if args.pointer:
                path = str(args.pointer.expanduser().resolve(strict=True))
                if not any(s["path"] == path and s["project"] == args.project for s in config["sources"]):
                    parser.error("register the pointer source in this project first")
                binding["pointer"] = path
            config["roles"][args.surface.upper()] = args.role
            config.setdefault("role_bindings", {}).pop(args.surface.upper(), None)
            if binding:
                config["role_bindings"][args.surface.upper()] = binding
        elif args.action in ("link", "unlink"):
            sender, receiver = args.sender.upper(), args.receiver.upper()
            if not all(re.fullmatch(r"[A-F0-9-]{36}", value) for value in (sender, receiver)) or sender == receiver:
                parser.error("use two distinct cmux surface UUIDs")
            if args.action == "link":
                source_path = str(args.source.expanduser().resolve(strict=True))
                source = next((s for s in config["sources"] if s["path"] == source_path), None)
                if source is None:
                    parser.error("register the route source first")
                content = read_source(source)
                lines = content["text"].splitlines()
                if content["error"] or not 0 < args.line <= len(lines):
                    parser.error("source line unavailable")
                item = {"from": sender, "to": receiver, "label": args.label,
                        "source": source_path, "line": args.line, "quote": lines[args.line - 1]}
            config["links"] = [item for item in config["links"] if (item["from"], item["to"]) != (sender, receiver)]
            if args.action == "link":
                config["links"].append(item)
        elif args.action == "set-workspaces-root":
            w9s_path = (args.w9s or args.path / "scripts" / "w9s").expanduser().resolve(strict=True)
            if not args.path.is_dir() or not w9s_path.is_file():
                parser.error("use a workspaces directory and a readable w9s script")
            config["workspaces_root"] = str(args.path)
            config["w9s_path"] = str(w9s_path)
        elif args.action == "set-tracing-url":
            config["claude_devtools_url"] = tracing.reader_url(args.url)
        save_config(args.config, config)
        print(f"Saved {args.config}")
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"control-room: {exc}\n")


if __name__ == "__main__":
    main()
