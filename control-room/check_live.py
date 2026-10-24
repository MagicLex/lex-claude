#!/usr/bin/env python3
"""Check a running room over HTTP and, optionally, its cmux browser pane."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

import app
from hooks import Hooks


def request(url, data=None, headers=None):
    try:
        with urlopen(Request(url, data=data, headers=headers or {}), timeout=10) as response:
            return response.status, response.read().decode(), response.headers
    except HTTPError as exc:
        return exc.code, exc.read().decode(), exc.headers


def check_http(url):
    code, html, headers = request(url)
    assert code == 200 and '<h1>' in html and '<main>' in html
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert headers["Cache-Control"] == "no-store"
    assert request(url + "/", headers={"Host": "evil.example"})[0] == 403
    base = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}"
    post = base + "/navigate"
    form = urlencode({"csrf": "wrong", "surface": "unknown"}).encode()
    for origin in ("https://evil.example", "null", base):
        assert request(post, form, {"Origin": origin})[0] == 403
    code, sessions, _ = request(base + "/?view=sessions")
    assert code == 200
    token = re.search(r'name="csrf" value="([^"]+)"', sessions)
    if not token:
        raise AssertionError("No live cmux navigation form available for CSRF checks")
    form = urlencode({"csrf": token[1], "surface": "no-such-surface"}).encode()
    assert request(post, form, {"Origin": base})[0] == 409
    assert request(base + "/source/../../etc/passwd")[0] == 404
    source_page = request(base + "/?view=sources")[1]
    sources = re.findall(r'href="(/source/[a-f0-9]{16})"', source_page)
    assert sources, "No registered sources to verify"
    for source in set(sources):
        code, html, _ = request(base + source)
        assert code == 200 and 'class="document"' in html
    print(f"HTTP: SSR, {len(set(sources))} sources, host, origin, CSRF, missing pane, and traversal checks passed")


def check_files():
    with tempfile.TemporaryDirectory(prefix="control-room-check-") as directory:
        path = Path(directory)
        app.command(["git", "init", "--quiet", str(path)])
        unborn = app.git_state(str(path))
        assert not unborn["error"] and not unborn["head"] and unborn["branch"]
        assert unborn["dirty"] is False
        app.command(["git", "-C", str(path), "-c", "user.name=Control room test", "-c", "user.email=test@localhost", "commit", "--quiet", "--allow-empty", "-m", "Test checkpoint"])
        clean = app.git_state(str(path))
        assert clean["head"] and clean["dirty"] is False
        source_path = path / "state.md"
        source_path.write_text("- Task: evidence pending\n")
        source = {"path": str(source_path), "label": "state", "project": "test", "kind": "blockers"}
        assert app.read_source(source)["text"] == "- Task: evidence pending\n"
        assert app.git_state(str(path))["dirty"] is True
        source_path.unlink()
        missing = app.read_source(source)
        assert missing["error"] and not missing["text"]
        source_path.write_bytes(b"x" * (app.SOURCE_LIMIT + 1))
        assert app.read_source(source)["error"]
        config_path = path / "config.json"
        config = app.read_config(config_path)
        config["sources"] = [source]
        app.save_config(config_path, config)
        assert config_path.stat().st_mode & 0o777 == 0o600
        room = app.Room(config_path, 15)
        room.snapshot = dict(room.snapshot, collected_at=time.time() - 100, sources=[{"text": "old"}])
        assert room.view()["sources"] == [] and room.view()["errors"]
    print("Files: real git unborn/clean/dirty, missing/oversized evidence, private config, expired snapshot checks passed")


def check_hooks():
    listener = Hooks(threading.Event())
    before = subprocess.run(["pgrep", "-P", str(os.getpid())], capture_output=True, text=True).stdout.split()
    listener.thread.start()
    try:
        deadline = time.monotonic() + 5
        while not listener.view()["connected"] and time.monotonic() < deadline:
            time.sleep(0.05)
        assert listener.view()["connected"], "cmux event subscription did not connect"
    finally:
        listener.close()
    assert not listener.thread.is_alive(), "Hook listener failed to stop"
    after = subprocess.run(["pgrep", "-P", str(os.getpid())], capture_output=True, text=True).stdout.split()
    assert before == after, "Hook child process survived shutdown"
    print("Hooks: real cmux subscription connected and stopped without a child process leak")


def check_role_pointers(url, config_path):
    config = app.read_config(config_path)
    bindings = [(anchor, binding) for anchor, binding in config.get("role_bindings", {}).items() if binding.get("pointer")]
    assert bindings, "No pointer bindings configured for the live role regression"
    base = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}"
    for anchor, binding in bindings:
        target = Path(binding["pointer"]).read_text().strip().upper()
        assert app.role_bindings.UUID.fullmatch(target), "Role pointer is not a surface UUID"
        code, html, _ = request(base + "/?" + urlencode({"view": "flow", "project": binding["project"]}))
        assert code == 200
        inspector = re.search(r'<article class="flow-detail" id="flow-' + re.escape(target) + r'"[^>]*>(.*?)</article>', html, re.S)
        assert inspector, f"Pointer targets {target}, but Flow has no role inspector for it"
        assigned = config["roles"][anchor]
        assigned = [assigned] if isinstance(assigned, str) else assigned
        assert app.e(" / ".join(assigned)) in inspector[1]
        assert app.e(binding["pointer"]) in inspector[1]
        assert f'data-from="{anchor}"' not in html or target == anchor
        assert f'data-to="{anchor}"' not in html or target == anchor
    print(f"Roles: {len(bindings)} live pointers agree with SSR roles, inspector evidence, and route endpoints")


def check_browser(surface, url, project, other_project):
    def browser(*args):
        return app.command(["cmux", "browser", surface, *args], timeout=10)

    def inspect(script):
        return json.loads(browser("eval", f"JSON.stringify({script})"))

    browser("navigate", url)
    assert inspect("innerWidth > 0 && !document.hidden"), "Focus the browser pane before checking its layout and refresh"
    for name in (other_project, project):
        browser("wait", "--selector", "#project", "--timeout", "5")
        browser("select", "--selector", "#project", "--value", name)
        expected = json.dumps(name)
        browser("wait", "--function", f"new URL(location.href).searchParams.get('project') === {expected}", "--timeout", "5")
        assert inspect("document.querySelector('#project').value") == name
        assert inspect("document.documentElement.scrollWidth <= innerWidth")
    browser("click", "--selector", 'a[href*="view=reviews"]')
    browser("wait", "--selector", "details.review", "--timeout", "5")
    browser("click", "--selector", "details.review summary")
    assert inspect("Boolean(document.querySelector('details.review[open] pre')?.textContent)")
    browser("viewport", "390", "844")
    assert inspect("document.documentElement.scrollWidth <= innerWidth")
    browser("viewport", "reset")
    browser("click", "--selector", 'nav a[href*="view=flow"]')
    browser("wait", "--selector", ".flow-node", "--timeout", "5")
    assert inspect("getComputedStyle(document.body).backgroundColor") == "rgb(255, 255, 255)"
    assert inspect("document.querySelectorAll('.setup-role').length") == 4
    assert inspect("document.querySelectorAll('.flow-edge').length") > 0
    browser("click", "--selector", ".flow-node")
    selected = inspect("location.hash")
    assert inspect("Boolean(document.querySelector('.flow-detail.selected form.navigate'))")
    browser("click", "--selector", '[data-zoom="in"]')
    zoom = inspect("document.querySelector('.flow-graph').getAttribute('viewBox')")
    assert zoom != inspect("document.querySelector('.flow-graph').dataset.fit")
    browser("eval", "document.querySelector('main').dataset.refreshCheck = 'old'")
    browser("wait", "--function", "!document.querySelector('main').dataset.refreshCheck", "--timeout", "6")
    assert inspect("location.hash") == selected
    assert inspect("document.querySelector('.flow-graph').getAttribute('viewBox')") == zoom
    assert inspect("Boolean(document.querySelector('.flow-detail.selected'))")
    browser("click", "--selector", '[data-zoom="fit"]')
    browser("viewport", "390", "844")
    assert inspect("document.documentElement.scrollWidth <= innerWidth")
    browser("viewport", "reset")
    browser("navigate", url)
    print("Browser: project switching, review disclosure, light Flow graph, role markers, selection/zoom across refresh, desktop/mobile overflow passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--browser")
    parser.add_argument("--project")
    parser.add_argument("--other-project")
    parser.add_argument("--config", type=Path, help="Check live role pointers against the running room")
    args = parser.parse_args()
    check_http(args.url)
    check_files()
    check_hooks()
    if args.config:
        check_role_pointers(args.url, args.config)
    if args.browser:
        if not args.project or not args.other_project:
            parser.error("browser checks need --project and --other-project")
        check_browser(args.browser, args.url, args.project, args.other_project)
