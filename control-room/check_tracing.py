"""Integration check against a running room and its local claude-devtools reader."""

import argparse
from html import unescape
from pathlib import Path
import re
from urllib.parse import urlsplit

import app
from check_live import request
import tracing
from trace_view import trace_url


def check(url, config_path):
    config = app.read_config(config_path)
    snapshot = app.collect(config)
    source = snapshot["tracing"]
    assert source["connected"] and not source["error"], source["error"]
    assert source["sessions"], "No retained Claude sessions in registered projects"
    row = next((r for r in source["sessions"] if r["has_subagents"]), source["sessions"][0])
    data = tracing.detail(config, row)
    assert data["groups"] and data["groups"][0]["metrics"]
    base = f'{urlsplit(url).scheme}://{urlsplit(url).netloc}'
    code, html, _ = request(base + trace_url(row))
    assert code == 200 and 'class="trace-detail"' in html
    assert 'data-trace-agent="main"' in html
    assert "Cache write" in html and "Cache read" in html
    assert not re.search(r'<iframe|<script[^>]*src="https?://', html)
    groups = re.findall(r'data-trace-agent="([^"]+)"', html)
    if len(groups) > 1:
        code, child, _ = request(base + trace_url(row, unescape(groups[1])))
        assert code == 200 and 'class="trace-detail"' in child
        assert 'Tool trace' in child and unescape(groups[1]) in child
    code, invalid, _ = request(base + '/?view=traces&trace=../../etc/passwd')
    assert code == 200 and 'no longer available' in invalid and 'class="trace-detail"' not in invalid
    disabled = tracing.catalog(dict(config, claude_devtools_url=None), snapshot["sessions"])
    assert not disabled["connected"] and not disabled["sessions"] and disabled["error"]
    print(f'Tracing: {len(source["sessions"])} real sessions, {len(groups)} agent rows, SSR detail, child drilldown, scoped lookup, disabled-reader hiding passed')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    check(args.url, args.config)
