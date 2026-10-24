import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

import app
import roles


class RoleUpdates(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="control-room-roles-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.lineage = self.directory / "lineage"
        self.lineage.mkdir()
        self.anchor, self.current, self.next_pane, self.gate = [str(uuid4()).upper() for _ in range(4)]
        self.parent, self.child, self.grandchild = [str(uuid4()).upper() for _ in range(3)]
        self.pointer = self.directory / "LEAD_SURFACE"
        self.pointer.write_text(self.current + "\n")
        self.route = self.directory / "handoff.md"
        self.route.write_text("Lead requests review from gate.\n")
        self.config = {"roles": {self.anchor: ["Lead"], self.gate: ["Gate", "Review"]},
                       "role_bindings": {self.anchor: {"project": "project", "pointer": str(self.pointer)}},
                       "sources": [self.source(self.pointer), self.source(self.route)],
                       "links": [{"from": self.anchor, "to": self.gate, "label": "Requests review",
                                  "source": str(self.route), "line": 1, "quote": self.route.read_text().strip()}]}
        self.sessions = [self.pane(self.anchor, self.parent), self.pane(self.current, self.child),
                         self.pane(self.gate)]

    def source(self, path):
        return {"path": str(path), "project": "project", "kind": "evidence", "label": path.name}

    def pane(self, surface, session="", project="project"):
        return {"id": surface, "session_id": session, "project": project, "workspace_title": surface,
                "state": "Unreported", "description": "", "detail": "", "runtime": "cmux"}

    def record(self, child, parent, generation):
        (self.lineage / child).write_text(f"{generation}\t{parent}\n")

    def resolve(self):
        sources = [app.read_source(source) for source in self.config["sources"]]
        endpoints, resolutions = roles.resolve(self.config, self.sessions, sources)
        return {"sources": sources, "links": self.config["links"], "role_endpoints": endpoints,
                "role_resolutions": resolutions}

    def follow_session(self):
        self.config["roles"][self.anchor] = ["Worker", "Docs"]
        self.config["role_bindings"][self.anchor] = {
            "project": "project", "session_id": self.parent, "lineage_dir": str(self.lineage)}

    def test_live_pointer_moves_role_routes_and_inspector_without_config_edit(self):
        snapshot = self.resolve()
        self.assertEqual(self.sessions[0]["roles"], [])
        self.assertEqual(self.sessions[1]["roles"], ["Lead"])
        self.assertEqual(app.flow_links(snapshot, self.sessions)[0][0]["from"], self.current)
        self.sessions.append(self.pane(self.next_pane, self.grandchild))
        self.pointer.write_text(self.next_pane + "\n")
        snapshot = self.resolve()
        self.assertEqual(self.sessions[1]["roles"], [])
        self.assertEqual(self.sessions[-1]["roles"], ["Lead"])
        self.assertEqual(app.flow_links(snapshot, self.sessions)[0][0]["from"], self.next_pane)
        html = app.render_flow(snapshot, self.sessions, "token")
        self.assertIn("Other panes (2)", html)
        self.assertNotIn(f'data-node="{self.anchor}"', html)
        self.assertNotIn(f'data-node="{self.current}"', html)
        self.assertIn(f'name="surface" value="{self.anchor}"', html)
        self.assertIn("Role evidence", html)
        self.assertIn(str(self.pointer), html)
        self.assertIn(app.source_url(self.source(self.pointer)) + "#L1", html)
        self.assertIn(f'data-bindings="{self.anchor}"', html)

    def test_pointer_failure_never_restores_old_lead_or_route(self):
        for content in ("", "not a uuid", self.current + "\n" + self.anchor, str(uuid4())):
            with self.subTest(content=content):
                self.pointer.write_text(content)
                snapshot = self.resolve()
                self.assertFalse(any("Lead" in row["roles"] for row in self.sessions))
                self.assertEqual(app.flow_links(snapshot, self.sessions), ([], 1))
                self.assertTrue(snapshot["role_resolutions"][0]["error"])
        self.pointer.unlink()
        self.assertEqual(self.resolve()["role_endpoints"][self.anchor], "")

    def test_pointer_scope_and_route_quote_remain_enforced(self):
        self.sessions[1]["project"] = "other"
        self.assertEqual(self.resolve()["role_endpoints"][self.anchor], "")
        self.sessions[1]["project"] = "project"
        self.route.write_text("Different instructions.\n")
        snapshot = self.resolve()
        self.assertEqual(snapshot["role_endpoints"][self.anchor], self.current)
        self.assertEqual(app.flow_links(snapshot, self.sessions), ([], 1))
        self.config["sources"][0]["project"] = "other"
        self.assertEqual(self.resolve()["role_endpoints"][self.anchor], "")

    def test_multigeneration_successor_moves_all_roles_and_both_route_directions(self):
        self.follow_session()
        self.config["links"].append(dict(self.config["links"][0], **{"from": self.gate, "to": self.anchor}))
        self.record(self.child, self.parent, 2)
        self.assertEqual(self.resolve()["role_endpoints"][self.anchor], self.current)
        self.record(self.grandchild, self.child, 3)
        snapshot = self.resolve()
        self.assertEqual(snapshot["role_endpoints"][self.anchor], "")
        self.assertEqual(self.sessions[1]["roles"], [])
        self.sessions.append(self.pane(self.next_pane, self.grandchild))
        snapshot = self.resolve()
        self.assertEqual(self.sessions[-1]["roles"], ["Worker", "Docs"])
        self.assertEqual(self.sessions[0]["roles"], [])
        self.assertEqual(self.sessions[1]["roles"], [])
        links, unavailable = app.flow_links(snapshot, self.sessions)
        self.assertEqual(unavailable, 0)
        self.assertEqual([(link["from"], link["to"]) for link in links],
                         [(self.next_pane, self.gate), (self.gate, self.next_pane)])
        evidence = snapshot["role_resolutions"][0]["evidence"]
        self.assertEqual([r["path"] for r in evidence], [str(self.lineage / self.child), str(self.lineage / self.grandchild)])
        self.assertIn(str(self.lineage / self.child), app.render_flow(snapshot, self.sessions, "token"))
        self.sessions.pop()
        self.assertEqual(self.resolve()["role_endpoints"][self.anchor], "")

    def test_ambiguous_lineage_duplicate_panes_and_wrong_project_fail_closed(self):
        self.follow_session()
        self.record(self.child, self.parent, 2)
        self.record(self.grandchild, self.parent, 2)
        self.assertIn("Ambiguous", self.resolve()["role_resolutions"][0]["error"])
        (self.lineage / self.grandchild).unlink()
        self.sessions.append(self.pane(self.next_pane, self.child))
        self.assertEqual(self.resolve()["role_endpoints"][self.anchor], "")
        self.sessions.pop()
        self.sessions[1]["project"] = "other"
        self.assertEqual(self.resolve()["role_endpoints"][self.anchor], "")

    def test_missing_corrupt_cyclic_and_inconsistent_lineage(self):
        self.follow_session()
        self.record(self.child, self.parent, 2)
        self.record(self.parent, self.child, 1)
        self.assertTrue(self.resolve()["role_resolutions"][0]["error"])
        (self.lineage / self.parent).unlink()
        self.record(self.grandchild, self.child, 9)
        self.assertIn("generation", self.resolve()["role_resolutions"][0]["error"])
        (self.lineage / self.grandchild).unlink()
        (self.lineage / self.child).write_text("broken")
        self.assertIn("Invalid lineage", self.resolve()["role_resolutions"][0]["error"])
        (self.lineage / self.child).write_bytes(b"x" * 4097)
        self.assertIn("Oversized", self.resolve()["role_resolutions"][0]["error"])
        (self.lineage / self.child).unlink()
        self.lineage.rmdir()
        self.assertEqual(self.resolve()["role_endpoints"][self.anchor], "")

    def test_current_session_and_legacy_pinned_surface_need_no_successor(self):
        self.follow_session()
        self.assertEqual(self.resolve()["role_endpoints"][self.anchor], self.anchor)
        self.assertEqual(self.sessions[0]["roles"], ["Worker", "Docs"])
        self.assertEqual(self.sessions[2]["roles"], ["Gate", "Review"])

    def test_titles_cannot_assign_roles_and_unmatched_session_cannot_receive_them(self):
        self.follow_session()
        self.record(self.child, self.parent, 2)
        self.sessions[1].update(id="", workspace_title="Lead", description="successor")
        self.assertEqual(self.resolve()["role_endpoints"][self.anchor], "")
        self.assertFalse(self.sessions[1]["roles"])

    def test_duplicate_lead_bindings_and_project_filtered_errors(self):
        self.config["roles"][self.current] = ["Lead"]
        snapshot = self.resolve()
        self.assertFalse(any("Lead" in row["roles"] for row in self.sessions))
        self.assertIn("Multiple lead bindings", app.render_flow(snapshot, self.sessions, "token"))
        self.assertNotIn("Multiple lead bindings", app.render_flow(snapshot, [], "token", "other"))


if __name__ == "__main__":
    unittest.main()
