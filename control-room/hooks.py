"""Read existing cmux hook events. Never install hooks or send agent input."""

from collections import deque
from datetime import datetime
import json
import os
import select
import subprocess
import threading
import time


HOOK_STATES = {
    "UserPromptSubmit": "working", "PreToolUse": "running",
    "PostToolUse": "working", "PostToolUseFailure": "working",
    "PermissionRequest": "needs input", "Stop": "idle", "SessionEnd": "ended",
}
ACTIVE_STATES = ("working", "running", "agents", "reviewing")


def hook_event(frame):
    if frame.get("type") != "event" or not frame.get("name", "").startswith("agent.hook."):
        return None
    payload = frame.get("payload") or {}
    surface = frame.get("surface_id") or payload.get("surface_id")
    if not surface:
        return None
    name = frame["name"].removeprefix("agent.hook.")
    try:
        occurred = datetime.fromisoformat(frame["occurred_at"].replace("Z", "+00:00")).timestamp()
    except (KeyError, TypeError, ValueError):
        return None
    return {"id": frame["id"], "surface": surface.upper(), "name": name,
            "state": HOOK_STATES.get(name), "tool": str(payload.get("tool_name") or "")[:120],
            "runtime": str(frame.get("source") or ""), "at": occurred}


class Hooks:
    def __init__(self, wake):
        self.wake = wake
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.events = deque(maxlen=100)
        self.states = {}
        self.last_frame = 0
        self.connected = False
        self.thread = threading.Thread(target=self.listen, name="room-hooks")

    def listen(self):
        while not self.stop.is_set():
            try:
                process = subprocess.Popen(["cmux", "events", "--category", "agent"],
                                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            except OSError:
                self.stop.wait(5)
                continue
            buffer = b""
            try:
                while not self.stop.is_set():
                    if not select.select([process.stdout], [], [], 0.5)[0]:
                        continue
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    buffer += chunk
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        try:
                            frame = json.loads(line)
                            event = hook_event(frame)
                        except (ValueError, KeyError, TypeError):
                            continue
                        with self.lock:
                            self.connected = True
                            self.last_frame = time.time()
                            if event:
                                self.events.append(event)
                                if event["state"]:
                                    self.states[event["surface"]] = event
                                    if len(self.states) > 256:
                                        oldest = min(self.states, key=lambda key: self.states[key]["at"])
                                        del self.states[oldest]
                        if event:
                            self.wake.set()
                    if len(buffer) > 65536:
                        raise ValueError("Oversized hook event")
            except (OSError, ValueError):
                pass
            finally:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
                process.stdout.close()
                with self.lock:
                    self.connected = False
            self.stop.wait(5)

    def view(self):
        with self.lock:
            connected = self.connected and time.time() - self.last_frame < 45
            return {"connected": connected, "events": list(self.events), "states": dict(self.states)}

    def close(self):
        self.stop.set()
        self.thread.join(timeout=7)
