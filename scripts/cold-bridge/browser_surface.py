"""Bound browser surface IPC for an isolated caller or Jev worker.

Only observed opaque IDs and named supplied values cross this interface. No browser
endpoint, credential, selector, JavaScript or global tab operation is available.
Direct callers can use this same class for ordinary programmatic automation.
"""

import copy
import json
import os
import time
import uuid
from pathlib import Path


class RemoteSurface:
    def __init__(self, *, directory=None, timeout_seconds=35):
        self.directory = Path(directory or os.environ["BROWSER_SURFACE_DIR"])
        self.timeout_seconds = timeout_seconds
        self.values = json.loads((self.directory / "contract.json").read_text())["values"]
        self._observed = {}

    def _call(self, op, **args):
        identifier = uuid.uuid4().hex
        request = {"id": identifier, "op": op, "args": args}
        body = json.dumps(request, ensure_ascii=False, allow_nan=False)
        if len(body.encode()) > 65536:
            raise ValueError("surface_request_too_large")
        temporary = self.directory / "requests" / (identifier + ".pending")
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.rename(self.directory / "requests" / (identifier + ".json"))
        response = self.directory / "responses" / (identifier + ".json")
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            if response.is_file():
                packet = json.loads(response.read_text())
                if not packet["ok"]:
                    raise RuntimeError(packet["error"])
                return packet["result"]
            time.sleep(0.02)
        raise RuntimeError("surface_submission_outcome_unknown_no_automatic_retry")

    def observe(self):
        snapshot = self._call("observe")
        self._observed[snapshot["ticket"]] = copy.deepcopy(snapshot)
        if len(self._observed) > 64:
            del self._observed[next(iter(self._observed))]
        return snapshot

    def _target(self, snapshot, action):
        retained = self._observed.get(snapshot.get("ticket"))
        if retained != snapshot:
            raise ValueError("snapshot_not_offered")
        if action is not None and action not in retained["actions"]:
            raise ValueError("target_not_offered")
        return snapshot["ticket"], action["id"] if action is not None else None

    def fresh(self, snapshot, action=None):
        ticket, action_id = self._target(snapshot, action)
        return self._call("fresh", ticket=ticket, action_id=action_id)

    def act(self, action, snapshot, text=None):
        ticket, action_id = self._target(snapshot, action)
        value_ref = None
        if text is not None:
            matches = [name for name, value in self.values.items() if value == text]
            if type(text) is not str or not matches:
                raise ValueError("supplied_named_value_required")
            value_ref = matches[0]
        return self._call("act", ticket=ticket, action_id=action_id, value_ref=value_ref)

    def settle(self, action):
        matches = [
            (ticket, snapshot)
            for ticket, snapshot in self._observed.items()
            if action in snapshot["actions"]
        ]
        if not matches:
            raise ValueError("target_not_offered")
        return self._call("settle", ticket=matches[-1][0], action_id=action["id"])

    def check_goal(self):
        """Read the shared controller's independent saved-state check; no effect."""
        return self._call("check_goal")
