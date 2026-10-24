from html import escape
import json
from urllib.parse import urlencode

from tracing import TOKEN_FIELDS, seconds, tool_calls


LABELS = ("Input", "Cache write", "Cache read", "Output")


def e(value):
    return escape(str(value), quote=True)


def trace_url(row, agent=None, tool_page=None):
    query = {"project": row["project"], "view": "traces", "trace": row["id"]}
    if agent:
        query["agent"] = agent
    if tool_page:
        query["tool_page"] = tool_page
    return "/?" + urlencode(query) + ("#trace-tools" if agent else "#trace-detail")


def cells(value):
    return ''.join(f'<td>{value[k]:,}</td>' if value else '<td>Unknown</td>' for k in TOKEN_FIELDS)


def pane_trace(snapshot, session):
    rows = snapshot.get("tracing", {}).get("sessions", [])
    return next((r for r in rows if session.get("session_id") and r["session_id"].lower() == session["session_id"].lower()
                 and r["project"] == session["project"]), None)


def pane_usage(snapshot, session):
    row = pane_trace(snapshot, session)
    if not row:
        return '<p class="quiet">Claude usage unavailable.</p>'
    value = row["metrics"]
    summary = f'{value["outputTokens"]:,} output · {value["cacheCreationTokens"]:,} cache write' if value else 'Usage unavailable'
    return f'<a class="trace-link" href="{e(trace_url(row))}"><b>Claude trace ↗</b><span>{summary}</span><small>Main conversation. Includes a separate subagent breakdown.</small></a>'


def table_header(first):
    return '<thead><tr><th>' + first + '</th>' + ''.join(f'<th>{name}</th>' for name in LABELS) + '</tr></thead>'


def timeline(waterfall):
    if not waterfall.get("minTime") or not waterfall.get("maxTime"):
        return '<p class="quiet">No timed events recorded.</p>'
    start, end = seconds(waterfall["minTime"]), seconds(waterfall["maxTime"])
    duration = max(end - start, 0.001)
    items = [item for item in waterfall.get("items", []) if item.get("type") == "subagent"]
    height = 42 + 28 * len(items)
    body = f'<div class="trace-timeline"><svg viewBox="0 0 900 {height}" role="img" aria-label="Subagent execution timeline">'
    body += '<rect class="trace-main-bar" x="180" y="8" width="710" height="12"/><text x="0" y="19">Main conversation</text>'
    for index, item in enumerate(items):
        x = 180 + 710 * (seconds(item["startTime"]) - start) / duration
        width = max(2, 710 * (seconds(item["endTime"]) - seconds(item["startTime"])) / duration)
        y = 36 + index * 28
        body += f'<text x="0" y="{y + 11}">{e(item["label"][:22])}</text><rect class="trace-agent-bar" x="{x:.2f}" y="{y}" width="{width:.2f}" height="12"><title>{e(item["label"])} · {e(item["startTime"])} to {e(item["endTime"])} · {e(item.get("durationMs", "Unknown"))} ms</title></rect>'
    body += '</svg></div>'
    body += f'<p class="quiet">{e(waterfall["minTime"])} to {e(waterfall["maxTime"])}</p>'
    return body


def render_traces(snapshot, selected, query, trace=None):
    source = snapshot.get("tracing", {})
    if source.get("error"):
        return f'<section><p class="alert">{e(source["error"])}</p></section>'
    rows = [r for r in source.get("sessions", []) if not selected or r["project"] == selected]
    body = '<section class="trace-section"><p class="quiet">Claude Code · local claude-devtools · retained session history. Token counters are usage, not current context size or a subscription bill.</p>'
    body += '<h2>Sessions</h2><p class="quiet">Up to 12 recent or pane-linked sessions per project. Main-conversation counters; open a trace for subagents.</p>'
    body += '<div class="trace-table"><table>' + table_header('Session') + '<tbody>'
    for row in rows:
        body += f'<tr data-trace-session="{e(row["id"])}"><td><a href="{e(trace_url(row))}">{e(row["label"])} ↗</a><small>{e(row["project"])} · {e(row["session_id"][:8])}</small></td>{cells(row["metrics"])}</tr>'
    body += '</tbody></table></div>'
    if not rows:
        body += '<p class="quiet">No retained Claude sessions found for this project.</p>'
    key = query.get("trace", [""])[0]
    if not key:
        return body + '</section>'
    row = next((r for r in rows if r["id"] == key), None)
    if not row:
        return body + '<p class="alert">Trace is no longer available in this project.</p></section>'
    if not trace or trace.get("error"):
        return body + f'<p class="alert">{e((trace or {}).get("error") or "Trace unavailable")}</p></section>'
    body += f'<section class="trace-detail" id="trace-detail"><h2>{e(row["label"])}</h2><p><code>{e(row["session_id"])}</code></p>'
    body += timeline(trace["waterfall"])
    body += '<h3>Agent usage</h3><p class="quiet">Each row counts that conversation only. Parent and child rows are separate.</p><div class="trace-table"><table>' + table_header('Agent') + '<tbody>'
    for group in trace["groups"]:
        body += f'<tr data-trace-agent="{e(group["id"])}"><td><a href="{e(trace_url(row, group["id"]))}">{e(group["label"])} ↗</a></td>{cells(group["metrics"])}</tr>'
    body += '</tbody></table></div>'
    group_id = query.get("agent", ["main"])[0]
    group = next((g for g in trace["groups"] if g["id"] == group_id), None)
    if group is None:
        return body + '<p class="alert">Agent not found in this trace.</p></section></section>'
    models = sorted({m["model"] for m in group["messages"] if m.get("model", "").startswith("claude-")})
    body += f'<h3 id="trace-tools">Tool trace · {e(group["label"])}</h3><p class="quiet">{e(", ".join(models))}</p>'
    calls = list(reversed(tool_calls(group["messages"])))
    pages = max(1, (len(calls) + 49) // 50)
    try:
        page = min(pages, max(1, int(query.get("tool_page", ["1"])[0])))
    except ValueError:
        page = 1
    body += f'<p class="quiet">{len(calls)} recorded tool calls · newest first · page {page} / {pages}</p>'
    for call in calls[(page - 1) * 50:page * 50]:
        result = call["result"]
        state = 'No result recorded' if result is None else 'Error' if result.get("isError") else 'Returned'
        payload = json.dumps(call["input"], ensure_ascii=False, indent=2)
        body += f'<details class="trace-call"><summary><b>{e(call["name"])}</b><time>{e(call["at"])}</time><span>{state}</span></summary><h4>Input</h4><pre>{e(payload[:65536])}</pre>'
        if len(payload) > 65536:
            body += '<p class="quiet">Input truncated at 65,536 characters.</p>'
        if result is not None:
            output = result.get("content", "")
            if not isinstance(output, str):
                output = json.dumps(output, ensure_ascii=False, indent=2)
            body += '<h4>Result</h4><pre>' + e(output[:65536]) + '</pre>'
            if len(output) > 65536:
                body += '<p class="quiet">Result truncated at 65,536 characters.</p>'
        body += '</details>'
    if page > 1:
        body += f'<a class="trace-page" href="{e(trace_url(row, group_id, page - 1))}">← Newer calls</a>'
    if page < pages:
        body += f'<a class="trace-page" href="{e(trace_url(row, group_id, page + 1))}">Older calls →</a>'
    return body + '</section></section>'
