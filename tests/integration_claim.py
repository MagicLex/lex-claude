#!/usr/bin/env python3
"""Tests for claim.py on a scratch claims dir, with real processes as holders.

Run from a Claude or Codex session (a lane): the discovery tests need a real
agent above them. Takes about three minutes (three waits on the 30 s poll).

  python3 tests/integration_claim.py
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

# Every run below gets the one resource the tests use; the real list comes from a repo's .claude/team.json.
os.environ["CLAIM_RESOURCES"] = "cluster"
CLAIM = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "team", "claim.py")


def sleeper():
    return subprocess.Popen(["sleep", "600"])


class Claims(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.procs = []

    def tearDown(self):
        for p in self.procs:
            p.kill()
            p.wait()

    def holder(self, kind="claude", session=None):
        p = sleeper()
        self.procs.append(p)
        return p, f"{kind} {session or f'S{p.pid}'} {p.pid}"

    def run_claim(self, *args, holder=None):
        env = {**os.environ, "CLAIM_DIR": self.dir}
        env.pop("CLAIM_HOLDER", None)
        if holder:
            env["CLAIM_HOLDER"] = holder
        return subprocess.run([sys.executable, CLAIM, *args], env=env, capture_output=True, text=True)

    def record(self, res="cluster"):
        with open(os.path.join(self.dir, res)) as f:
            return json.load(f)

    def test_discovery_finds_this_agent_across_separate_calls(self):
        self.assertEqual(self.run_claim("take", "cluster", "t").returncode, 0)
        rec = self.record()
        self.assertIn(rec["kind"], ("claude", "codex"))
        ancestors, pid = set(), os.getpid()
        while pid > 1:
            ancestors.add(pid)
            pid = int(subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True).stdout)
        self.assertIn(rec["pid"], ancestors)
        # Each call is its own process: the holder is the agent, not the shell that made the call.
        self.assertEqual(self.run_claim("check", "cluster", "--held").returncode, 0)
        self.assertEqual(self.run_claim("release", "cluster").returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "cluster")))

    def test_second_holder_refused_and_cannot_release(self):
        _, a = self.holder()
        _, b = self.holder()
        self.assertEqual(self.run_claim("take", "cluster", "a", holder=a).returncode, 0)
        r = self.run_claim("take", "cluster", "b", holder=b)
        self.assertEqual(r.returncode, 3)
        self.assertIn("held by", r.stderr)
        self.assertEqual(self.run_claim("check", "cluster", "--held", holder=b).returncode, 3)
        self.assertEqual(self.run_claim("check", "cluster", holder=b).returncode, 3)
        self.assertEqual(self.run_claim("release", "cluster", holder=b).returncode, 1)
        self.assertEqual(self.record()["session"], a.split()[1])

    def test_holder_take_again_updates_intent_and_keeps_since(self):
        _, a = self.holder()
        self.assertEqual(self.run_claim("take", "cluster", "first", holder=a).returncode, 0)
        since = self.record()["since"]
        r = self.run_claim("take", "cluster", "second", holder=a)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.record()["intent"], "second")
        self.assertEqual(self.record()["since"], since)

    def test_status_lists_a_claim_this_script_does_not_name(self):
        # A checkout behind main must still show a claim on a resource main added since.
        _, a = self.holder()
        self.assertEqual(self.run_claim("take", "cluster", "a", holder=a).returncode, 0)
        os.rename(os.path.join(self.dir, "cluster"), os.path.join(self.dir, "cluster-later"))
        out = self.run_claim("status").stdout
        self.assertIn("cluster-later held by", out)
        self.assertNotIn("no claims", out)

    def test_free_resource_passes_plain_check_but_not_held(self):
        _, a = self.holder()
        self.assertEqual(self.run_claim("check", "train", holder=a).returncode, 0)
        self.assertEqual(self.run_claim("check", "train", "--held", holder=a).returncode, 3)

    def test_stale_claim_refuses_until_over_names_its_session(self):
        pa, a = self.holder(session="SA")
        _, b = self.holder()
        self.assertEqual(self.run_claim("take", "cluster", "a", holder=a).returncode, 0)
        pa.kill()
        pa.wait()
        r = self.run_claim("take", "cluster", "b", holder=b)
        self.assertEqual(r.returncode, 3)
        self.assertIn("STALE", r.stderr)
        self.assertEqual(self.run_claim("check", "cluster", holder=b).returncode, 3)
        self.assertEqual(self.run_claim("take", "cluster", "b", "--over", "SX", holder=b).returncode, 3)
        self.assertEqual(self.run_claim("take", "cluster", "b", "--over", "SA", holder=b).returncode, 0)
        self.assertEqual(self.record()["session"], b.split()[1])

    def test_over_never_takes_a_live_claim(self):
        _, a = self.holder(session="SA")
        _, b = self.holder()
        self.run_claim("take", "cluster", "a", holder=a)
        self.assertEqual(self.run_claim("take", "cluster", "b", "--over", "SA", holder=b).returncode, 3)
        self.assertEqual(self.record()["session"], "SA")

    def test_reused_pid_with_another_start_time_is_stale(self):
        p, a = self.holder(kind="codex", session="codex-1")
        self.run_claim("take", "cluster", "a", holder=a)
        rec = self.record()
        rec["start"] = "Thu Jan  1 00:00:00 1970"
        with open(os.path.join(self.dir, "cluster"), "w") as f:
            json.dump(rec, f)
        _, b = self.holder()
        self.assertIn("STALE", self.run_claim("take", "cluster", "b", holder=b).stderr)
        # The same codex id on the same pid is not the holder either: its start time differs.
        self.assertEqual(self.run_claim("check", "cluster", "--held", holder=a).returncode, 3)

    def test_claude_session_moved_to_a_new_pid_keeps_its_claim(self):
        pa, a = self.holder(kind="claude", session="SM")
        self.run_claim("take", "cluster", "a", holder=a)
        pa.kill()
        pa.wait()
        pb, b = self.holder(kind="claude", session="SM")
        self.assertEqual(self.run_claim("check", "cluster", "--held", holder=b).returncode, 0)
        self.assertEqual(self.record()["pid"], pb.pid)
        _, c = self.holder(kind="codex", session="SM")
        self.assertEqual(self.run_claim("check", "cluster", "--held", holder=c).returncode, 3)

    def test_two_takers_of_one_stale_claim_one_wins(self):
        pa, a = self.holder(session="SA")
        self.run_claim("take", "cluster", "a", holder=a)
        pa.kill()
        pa.wait()
        takers = [self.holder() for _ in range(8)]
        env = {**os.environ, "CLAIM_DIR": self.dir}
        runs = [subprocess.Popen([sys.executable, CLAIM, "take", "cluster", "x", "--over", "SA"],
                                 env={**env, "CLAIM_HOLDER": h}, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                for _, h in takers]
        codes = [r.communicate() and r.returncode for r in runs]
        self.assertEqual(sorted(codes), [0] + [3] * 7)
        winner = takers[codes.index(0)][1].split()[1]
        self.assertEqual(self.record()["session"], winner)

    def test_reader_never_sees_a_partial_claim(self):
        _, a = self.holder()
        reader = subprocess.Popen(
            [sys.executable, "-c",
             "import json,os,sys,time\n"
             "p=os.path.join(sys.argv[1],'cluster'); end=time.time()+8; bad=0\n"
             "while time.time()<end:\n"
             "  try:\n"
             "    with open(p) as f: json.load(f)\n"
             "  except FileNotFoundError: pass\n"
             "  except ValueError: bad+=1\n"
             "print(bad)", self.dir], stdout=subprocess.PIPE, text=True)
        end = time.time() + 7
        while time.time() < end:
            self.run_claim("take", "cluster", "x" * 4096, holder=a)
            self.run_claim("release", "cluster", holder=a)
        self.assertEqual(reader.communicate()[0].strip(), "0")

    def test_wait_takes_once_released_and_gives_up_at_its_bound(self):
        _, a = self.holder()
        _, b = self.holder()
        self.run_claim("take", "cluster", "a", holder=a)
        env = {**os.environ, "CLAIM_DIR": self.dir, "CLAIM_HOLDER": b}
        waiter = subprocess.Popen([sys.executable, CLAIM, "take", "cluster", "b", "--wait", "2"],
                                  env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(3)
        self.assertEqual(self.run_claim("release", "cluster", holder=a).returncode, 0)
        waiter.communicate(timeout=90)
        self.assertEqual(waiter.returncode, 0)
        self.assertEqual(self.record()["session"], b.split()[1])
        t0 = time.time()
        r = self.run_claim("take", "cluster", "a", "--wait", "1", holder=a)
        self.assertEqual(r.returncode, 3)
        self.assertGreaterEqual(time.time() - t0, 59)
        self.assertLess(time.time() - t0, 71)

    def test_wait_sees_a_release_in_its_last_poll_interval(self):
        _, a = self.holder()
        _, b = self.holder()
        self.run_claim("take", "cluster", "a", holder=a)
        env = {**os.environ, "CLAIM_DIR": self.dir, "CLAIM_HOLDER": b}
        t0 = time.time()
        waiter = subprocess.Popen([sys.executable, CLAIM, "take", "cluster", "b", "--wait", "1"],
                                  env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # Checks run at 0, 30 and 60 s: a release at 40 s is seen only by the final check at the bound.
        time.sleep(40)
        self.assertEqual(self.run_claim("release", "cluster", holder=a).returncode, 0)
        waiter.communicate(timeout=60)
        self.assertEqual(waiter.returncode, 0)
        self.assertGreaterEqual(time.time() - t0, 59)
        self.assertEqual(self.record()["session"], b.split()[1])

    def test_usage_errors(self):
        _, a = self.holder()
        self.assertEqual(self.run_claim("take", "nope", "x", holder=a).returncode, 1)
        self.assertEqual(self.run_claim("take", "cluster", holder=a).returncode, 1)
        self.assertEqual(self.run_claim("take", "cluster", "x", "--wait", "0", holder=a).returncode, 1)

    def sessions_file(self, **records):
        d = tempfile.mkdtemp()
        for i, rec in enumerate(records.values()):
            with open(os.path.join(d, f"{i}.json"), "w") as f:
                json.dump(rec, f)
        return os.path.join(d, "*.json")

    def test_name_follows_a_moved_session_to_its_live_process(self):
        old, new = sleeper(), sleeper()
        self.procs += [old, new]
        old.kill()
        old.wait()
        sid = "0A1B2C3D-0000-4000-8000-00000000AB12"
        pattern = self.sessions_file(
            gone={"pid": old.pid, "sessionId": sid, "name": "hopsable-old"},
            live={"pid": new.pid, "sessionId": sid, "name": "hopsable-new"},
            other={"pid": new.pid, "sessionId": "FFFFFFFF-0000-4000-8000-000000000000", "name": "hopsable-other"})
        env = {**os.environ, "CLAIM_DIR": self.dir, "CLAIM_SESSIONS": pattern}
        r = subprocess.run([sys.executable, CLAIM, "name", sid.lower()], env=env, capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "hopsable-new"))
        r = subprocess.run([sys.executable, CLAIM, "name", "11111111-0000-4000-8000-000000000000"], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 3)

    def test_name_of_a_session_whose_process_is_gone_is_refused(self):
        p = sleeper()
        p.kill()
        p.wait()
        sid = "0A1B2C3D-0000-4000-8000-00000000CD34"
        env = {**os.environ, "CLAIM_DIR": self.dir,
               "CLAIM_SESSIONS": self.sessions_file(gone={"pid": p.pid, "sessionId": sid, "name": "hopsable-gone"})}
        r = subprocess.run([sys.executable, CLAIM, "name", sid], env=env, capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout), (3, ""))

    def test_whoami_prints_the_lane_line_name_and_id(self):
        p, h = self.holder(session="0A1B2C3D-0000-4000-8000-00000000EF56")
        env = {**os.environ, "CLAIM_DIR": self.dir, "CLAIM_HOLDER": h, "CLAIM_SESSIONS": self.sessions_file(
            me={"pid": p.pid, "sessionId": "0A1B2C3D-0000-4000-8000-00000000EF56", "name": "hopsable-me"})}
        r = subprocess.run([sys.executable, CLAIM, "whoami"], env=env, capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), "hopsable-me 0A1B2C3D-0000-4000-8000-00000000EF56")

    def test_a_session_file_with_bytes_after_its_object_is_read(self):
        # Claude Code can rewrite a shorter session file in place, leaving the old file's last bytes after the object.
        p = sleeper()
        self.procs.append(p)
        sid = "0A1B2C3D-0000-4000-8000-00000000AA77"
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "0.json"), "w") as f:
            f.write(json.dumps({"pid": p.pid, "sessionId": sid, "name": "hopsable-trailing"}) + "}")
        env = {**os.environ, "CLAIM_DIR": self.dir, "CLAIM_SESSIONS": os.path.join(d, "*.json")}
        r = subprocess.run([sys.executable, CLAIM, "name", sid], env=env, capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "hopsable-trailing"))

    def test_whoami_from_this_agent(self):
        r = subprocess.run([sys.executable, CLAIM, "whoami"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        name, session = r.stdout.split()
        self.assertTrue(name and session)


if __name__ == "__main__":
    unittest.main(verbosity=2)
