import unittest

import tracing
from trace_view import render_traces, timeline


class Tracing(unittest.TestCase):
    def test_reader_rejects_external_or_credential_urls(self):
        for value in ("https://127.0.0.1:80", "http://example.com:80", "http://127.0.0.1:80@evil.example:80",
                      "http://user@localhost:80", "http://localhost:80/path", "http://localhost:80?url=evil", "file:///tmp/log"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                tracing.reader_url(value)
        self.assertEqual(tracing.reader_url("http://127.0.0.1:1234/"), "http://127.0.0.1:1234")

    def test_unknown_counters_are_not_zero(self):
        self.assertIsNone(tracing.metrics(None))
        self.assertIsNone(tracing.metrics({"outputTokens": 0}))
        zero = dict.fromkeys(tracing.TOKEN_FIELDS, 0)
        self.assertEqual(tracing.metrics(zero), zero)
        self.assertIsNone(tracing.metrics(dict(zero, inputTokens=-1)))
        self.assertIsNone(tracing.metrics(dict(zero, inputTokens=True)))

    def test_empty_timeline_has_no_invented_dates(self):
        self.assertIn("No timed events", timeline({"items": [], "minTime": None, "maxTime": None}))

    def test_failed_reader_hides_old_sessions(self):
        html = render_traces({"tracing": {"error": "Reader offline", "sessions": [{"project": "old"}]}}, "", {})
        self.assertIn("Reader offline", html)
        self.assertNotIn("data-trace-session", html)

    def test_trace_lookup_cannot_cross_project_filter(self):
        row = {"id": "a", "project": "private", "label": "private session", "session_id": "s", "metrics": None}
        html = render_traces({"tracing": {"sessions": [row]}}, "other", {"trace": ["a"]})
        self.assertNotIn("private session", html)
        self.assertIn("no longer available", html)


if __name__ == "__main__":
    unittest.main()
