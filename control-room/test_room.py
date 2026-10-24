import unittest

import app
from hooks import hook_event


class Reviews(unittest.TestCase):
    def test_latest_verdict_and_latest_order(self):
        text = "alpha aaaaaaa: FIX (code)\nold\nbeta bbbbbbb: PASS (code)\nalpha ccccccc: PASS (code)\nnew"
        entries = app.review_entries(text)
        self.assertEqual([(r["subject"], r["commit"], r["verdict"]) for r in entries],
                         [("alpha", "ccccccc", "PASS"), ("beta", "bbbbbbb", "PASS")])
        self.assertEqual(entries[0]["line"], 4)
        self.assertNotIn("old", entries[0]["text"])

    def test_multiple_repositories_never_bind_to_one_commit(self):
        for header in ("api aaaaaaa + helm bbbbbbb: PASS (code)",
                       "api aaaaaaa: PASS; helm bbbbbbb: FIX (code)"):
            with self.subTest(header=header):
                entry = app.review_entries(header)[0]
                self.assertEqual(entry["commit"], "")
                self.assertEqual(entry["text"], header)

    def test_hashless_draft_preserves_source(self):
        header = "Jira draft: FIX (SHA256 " + "a" * 64 + ")\nMissing evidence."
        entry = app.review_entries(header)[0]
        self.assertEqual(entry["commit"], "")
        self.assertEqual(entry["text"], header)

    def test_commit_match_does_not_approve_dirty_work_or_changed_head(self):
        entry = {"subject": "task", "commit": "abcdef0", "verdict": "PASS"}
        git = {"head": "abcdef0" + "a" * 33, "dirty": False, "error": ""}
        self.assertEqual(app.review_binding(entry, {"task": git})[0], "Commit matches")
        self.assertEqual(app.review_binding(entry, {"task": dict(git, dirty=True)})[0], "Revalidation needed")
        self.assertEqual(app.review_binding(entry, {"task": dict(git, head="b" * 40)})[0], "Revalidation needed")
        self.assertEqual(app.review_binding(entry, {"task": dict(git, error="unavailable")})[0], "Target unavailable")
        self.assertEqual(app.review_binding(entry, {})[0], "Unbound review")


class Content(unittest.TestCase):
    def test_selected_project_survives_empty_snapshot(self):
        snapshot = {"collected_at": 0, "sessions": [], "sources": [], "projects": [],
                    "targets": {}, "jobs": [], "errors": ["Collecting local sources"]}
        html = app.render(snapshot, "token", {"project": ["Selected project"]})
        self.assertIn('<option value="Selected project" selected>Selected project</option>', html)

    def test_longest_project_boundary(self):
        projects = [{"name": "root", "path": "/work/project"}, {"name": "nested", "path": "/work/project/nested"}]
        self.assertEqual(app.project_for("/work/project/nested/src", projects), "nested")
        self.assertEqual(app.project_for("/work/project-other", projects), "Unassigned")

    def test_work_notes_do_not_infer_status_or_include_nested_steps(self):
        self.assertEqual(app.work_notes("# State\n- Item: tests pending\n  - nested\n- Done?"),
                         [(2, "Item: tests pending"), (4, "Done?")])

    def test_source_links_survive_relabeling(self):
        first = {"path": "/work/verdicts.md", "label": "Old"}
        second = dict(first, label="New")
        self.assertEqual(app.source_url(first), app.source_url(second))
        self.assertNotEqual(app.source_url(first), app.source_url(dict(first, path="/work/other.md")))

    def test_untrusted_source_and_query_are_escaped(self):
        attack = '<script>alert("x")</script>'
        source = {"project": "test", "path": "/review.md", "label": attack, "kind": "review",
                  "text": f"{attack} aaaaaaa: FIX\n{attack}", "modified": 1, "error": ""}
        snapshot = {"collected_at": 1, "sessions": [], "sources": [source], "projects": [], "targets": {}, "jobs": [], "errors": []}
        html = app.render(snapshot, 'token"injection', {"view": ["reviews"]})
        self.assertNotIn(attack, html)
        self.assertIn("&lt;script&gt;", html)
        html = app.render(snapshot, "token", {"project": [attack]})
        self.assertNotIn(attack, html)


class Flow(unittest.TestCase):
    def test_routes_require_unchanged_evidence_and_same_project(self):
        sessions = [{"id": "lead", "project": "project"}, {"id": "worker", "project": "project"}]
        source = {"path": "/handoff.md", "project": "project", "text": "Lead coordinates worker.", "error": ""}
        link = {"from": "lead", "to": "worker", "label": "Coordinates", "source": source["path"],
                "line": 1, "quote": source["text"]}
        snapshot = {"sources": [source], "links": [link]}
        self.assertEqual(len(app.flow_links(snapshot, sessions)[0]), 1)
        for changed in (dict(source, text="Different work."), dict(source, error="Missing"), dict(source, project="other")):
            self.assertEqual(app.flow_links(dict(snapshot, sources=[changed]), sessions), ([], 1))
        self.assertEqual(app.flow_links(snapshot, sessions[:1]), ([], 1))
        self.assertEqual(app.flow_links(snapshot, []), ([], 0))

    def test_setup_does_not_invent_agents_or_links(self):
        snapshot = {"sources": [], "links": []}
        html = app.render_flow(snapshot, [], "token")
        self.assertEqual(html.count("Not assigned"), 4)
        self.assertEqual(html.count("<b>Gate / Invariants</b>"), 1)
        self.assertNotIn("<b>Invariants</b>", html)
        self.assertNotIn('class="flow-edge"', html)
        self.assertIn("No panes reported", html)

    def test_hook_stop_is_idle_and_subagent_stop_does_not_stop_parent(self):
        frame = {"type": "event", "name": "agent.hook.PreToolUse", "id": "event-1",
                 "surface_id": "pane", "source": "claude", "occurred_at": "2026-10-24T07:00:00Z",
                 "payload": {"tool_name": "Bash"}}
        event = hook_event(frame)
        self.assertEqual((event["state"], event["surface"], event["tool"]), ("running", "PANE", "Bash"))
        self.assertEqual(hook_event(dict(frame, name="agent.hook.Stop"))["state"], "idle")
        self.assertIsNone(hook_event(dict(frame, name="agent.hook.SubagentStop"))["state"])
        self.assertIsNone(hook_event(dict(frame, name="feed.item.completed")))
        self.assertIsNone(hook_event(dict(frame, surface_id=None)))
        self.assertIsNone(hook_event(dict(frame, occurred_at="unknown")))

    def test_unmapped_pane_remains_navigable_outside_team_graph(self):
        session = {"id": "pane", "role": "Unassigned", "roles": [], "project": "project",
                   "workspace_title": "Previous session", "description": "", "state": "Unreported"}
        html = app.render_flow({"sources": [], "links": []}, [session], "token")
        self.assertNotIn('data-node="pane"', html)
        self.assertIn("Other panes (1)", html)
        self.assertIn('name="surface" value="pane"', html)


if __name__ == "__main__":
    unittest.main()
