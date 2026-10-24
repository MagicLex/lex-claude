"""Read-only adapter for the local claude-devtools HTTP API (tested with 0.5.0)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener


TOKEN_FIELDS = ("inputTokens", "cacheCreationTokens", "cacheReadTokens", "outputTokens")
RESPONSE_LIMIT = 64 * 1024 * 1024
SESSION_LIMIT = 12


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def reader_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1")
            or parsed.username or parsed.password or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment or not parsed.port):
        raise ValueError("Trace reader must be a loopback HTTP URL with a port")
    return value.rstrip("/")


def get(base, path):
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(reader_url(base) + path, timeout=5) as response:
        content = response.read(RESPONSE_LIMIT + 1)
    if len(content) > RESPONSE_LIMIT:
        raise ValueError("Trace response exceeds 64 MiB")
    return json.loads(content)


def session_path(row):
    return f'/api/projects/{quote(row["reader_project"], safe="")}/sessions/{quote(row["session_id"], safe="")}'


def metrics(value):
    if not isinstance(value, dict):
        return None
    if any(not isinstance(value.get(k), int) or isinstance(value[k], bool) or value[k] < 0 for k in TOKEN_FIELDS):
        return None
    return {k: value[k] for k in TOKEN_FIELDS}


def catalog(config, panes):
    base = config.get("claude_devtools_url")
    result = {"sessions": [], "error": "", "connected": False, "available": 0}
    if not base:
        result["error"] = "Claude trace reader is not connected."
        return result
    try:
        projects = get(base, "/api/projects")
        if not isinstance(projects, list):
            raise ValueError("Invalid trace project list")
        registered = []
        for project in projects:
            path = Path(project["path"])
            matches = [p for p in config["projects"] if path == Path(p["path"]) or Path(p["path"]) in path.parents]
            if matches:
                registered.append((project, max(matches, key=lambda p: len(p["path"]))["name"]))
        rows = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            pending = [(project, name, pool.submit(get, base, f'/api/projects/{quote(project["id"], safe="")}/sessions'))
                       for project, name in registered]
            for project, name, future in pending:
                entries = future.result()
                if not isinstance(entries, list):
                    raise ValueError("Invalid trace session list")
                for entry in entries:
                    sid = entry["id"]
                    bound = [p for p in panes if p.get("session_id", "").lower() == sid.lower() and p["project"] == name]
                    rows.append({"id": sha256((project["id"] + "/" + sid).encode()).hexdigest()[:16],
                                 "reader_project": project["id"], "session_id": sid, "project": name,
                                 "label": bound[0]["workspace_title"] if bound else sid[:8],
                                 "pane": bound[0]["id"] if bound else "", "updated": entry.get("updatedAt", 0),
                                 "has_subagents": entry.get("hasSubagents", False), "metrics": None})
        result["available"] = len(rows)
        chosen = []
        for name in sorted({r["project"] for r in rows}):
            candidates = sorted((r for r in rows if r["project"] == name), key=lambda r: (bool(r["pane"]), r["updated"]), reverse=True)
            chosen.extend(candidates[:SESSION_LIMIT])
        with ThreadPoolExecutor(max_workers=4) as pool:
            pending = [(row, pool.submit(get, base, session_path(row) + "/metrics")) for row in chosen]
            for row, future in pending:
                row["metrics"] = metrics(future.result())
        result.update(sessions=chosen, connected=True)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result.update(sessions=[], error=f"Claude trace reader unavailable: {exc}")
    return result


def detail(config, row):
    base = config.get("claude_devtools_url", "")
    with ThreadPoolExecutor(max_workers=2) as pool:
        data = pool.submit(get, base, session_path(row))
        waterfall = pool.submit(get, base, session_path(row) + "/waterfall")
        data, waterfall = data.result(), waterfall.result()
    if not isinstance(data, dict) or not isinstance(waterfall, dict):
        raise ValueError("Session trace is unavailable")
    groups = [{"id": "main", "label": "Main conversation", "metrics": metrics(data.get("metrics")),
               "messages": data.get("messages", [])}]
    seen = set()
    for process in data.get("processes", []):
        if process["id"] in seen:
            continue
        seen.add(process["id"])
        groups.append({"id": process["id"], "label": process.get("description") or process["id"],
                       "metrics": metrics(process.get("metrics")), "messages": process.get("messages", [])})
    return {"groups": groups, "waterfall": waterfall}


def tool_calls(messages):
    calls, results = {}, {}
    for message in messages:
        for call in message.get("toolCalls", []):
            calls.setdefault(call["id"], {"id": call["id"], "name": call["name"], "input": call.get("input"),
                                           "at": message.get("timestamp"), "result": None})
        for result in message.get("toolResults", []):
            results[result["toolUseId"]] = result
    for key, call in calls.items():
        call["result"] = results.get(key)
    return sorted(calls.values(), key=lambda call: call["at"] or "")


def seconds(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
