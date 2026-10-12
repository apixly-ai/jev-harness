"""Browser cold-authoring capability and independent result boundaries."""

import copy
import importlib
import json
from pathlib import Path

import pytest
from platform_support import WINDOWS, make_junction


@pytest.fixture
def browser(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "benchmarks"))
    return importlib.import_module("browser_cold")


class FakeSurface:
    owned = True

    def __init__(self):
        self.changed, self.calls, self.closed, self.fail = False, [], False, False
        self.actions = [
            {"id": "c1", "node": 42, "kind": "click", "label": "Save draft", "role": "button"},
            {"id": "f2", "node": 45, "kind": "fill", "label": "Title", "role": "textbox"},
            {"id": "c3", "node": 46, "kind": "click", "label": "Send now", "role": "button"},
            {"id": "c4", "node": 47, "kind": "click", "label": "Delete draft", "role": "button"},
            {"id": "f5", "node": 48, "kind": "fill", "label": "Password", "sensitive": True},
        ]

    def observe(self):
        return {
            "url": "http://127.0.0.1:8001/",
            "title": "Draft settings",
            "text": "Draft settings",
            "fingerprint": "changed" if self.changed else "stable",
            "actions": copy.deepcopy(self.actions),
            "page_key": "private-page",
            "guards": {"42": "private-guard"},
            "marker": "private-marker",
        }

    def fresh(self, state, action=None):
        return not self.changed

    def act(self, action, state, text=None):
        self.calls.append((copy.deepcopy(action), copy.deepcopy(state), text))
        if self.fail:
            raise RuntimeError("transport failed after possible effect")
        return {"executed": action["id"]}

    def settle(self, action):
        pass

    def close(self):
        self.closed = True


def broker_for(browser, surface=None, **kwargs):
    surface = surface or FakeSurface()
    return browser.BrowserBroker(
        surface,
        allowed_origin="http://127.0.0.1:8001",
        values={"title": "Failure summary", "note": "Preview only"},
        check_goal=lambda: {"passed": False, "problems": ["not_saved"]},
        **kwargs,
    )


def test_observation_is_stable_opaque_and_excludes_unsafe_controls(browser):
    broker = broker_for(browser)
    first, second = broker.observe(), broker.observe()
    assert first == second
    assert len(first["actions"]) == 2
    assert {a["label"] for a in first["actions"]} == {"Save draft", "Title"}
    encoded = json.dumps(first)
    assert "private-" not in encoded and '"node"' not in encoded
    assert "selector" not in encoded and "guards" not in encoded
    assert all(a["id"] not in {"c1", "f2"} for a in first["actions"])


def test_broker_reconstructs_retained_target_and_named_fill(browser):
    surface = FakeSurface()
    broker = broker_for(browser, surface)
    seen = broker.observe()
    fill = next(a for a in seen["actions"] if a["kind"] == "fill")
    broker.act(seen["ticket"], fill["id"], value_ref="title")
    actual, snapshot, text = surface.calls[0]
    assert actual["node"] == 45 and snapshot["page_key"] == "private-page"
    assert text == "Failure summary" and broker.effects == 1
    with pytest.raises(ValueError, match="named_value"):
        broker.act(seen["ticket"], fill["id"], value_ref="arbitrary user text")
    assert len(surface.calls) == 1


def test_unknown_and_unobserved_targets_cannot_execute(browser):
    broker = broker_for(browser)
    seen = broker.observe()
    for ticket, target in [("fake", seen["actions"][0]["id"]), (seen["ticket"], "c1")]:
        with pytest.raises(ValueError, match="observed"):
            broker.act(ticket, target)
    assert broker.effects == 0 and broker.surface.calls == []


def test_stale_origin_budget_and_uncertain_effects_stop_before_retry(browser):
    surface = FakeSurface()
    broker = broker_for(browser, surface, max_effects=1)
    seen = broker.observe()
    surface.changed = True
    assert broker.fresh(seen["ticket"], seen["actions"][0]["id"]) is False
    with pytest.raises(ValueError, match="stale"):
        broker.act(seen["ticket"], seen["actions"][0]["id"])
    assert not surface.calls
    surface.changed = False
    surface.fail = True
    with pytest.raises(RuntimeError):
        broker.act(seen["ticket"], seen["actions"][0]["id"])
    assert broker.uncertain is True and broker.effects == 1
    with pytest.raises(ValueError, match="uncertain"):
        broker.act(seen["ticket"], seen["actions"][0]["id"])
    assert len(surface.calls) == 1
    assert broker.check_goal()["passed"] is False


def test_independent_check_uses_saved_backend_values_not_confirmation_copy(browser):
    case = browser.case_contract(0)
    state = browser.DraftState(case)
    assert not state.check_goal()["passed"]
    expected = state.expected()
    wrong = {**expected, "projects": []}
    state.save(wrong)
    assert state.check_goal()["passed"] is False
    assert "projects" in state.check_goal()["problems"]
    correct = browser.DraftState(case)
    correct.save(correct.expected())
    assert correct.check_goal()["passed"] is True
    assert correct.snapshot()["save_attempts"] == 1
    correct.save(correct.expected())
    assert correct.check_goal()["passed"] is False


def test_actor_contract_has_constraints_not_project_answers_or_route_preference(browser):
    case = browser.case_contract(0)
    prompt = browser.actor_prompt(case)
    assert case["values"]["title"] in prompt and case["timezone"] in prompt
    assert "active production projects" in prompt and "draft" in prompt
    assert "prefer" not in prompt.lower() and "Jev" not in prompt
    assert "aurora" not in prompt.lower() and "cedar" not in prompt.lower()
    native, optional = browser.tools(False), browser.tools(True, live=True)
    assert {t["name"] for t in optional} - {t["name"] for t in native} == {"run_script"}
    assert "shell" in {t["name"] for t in native}
    assert "check_goal" in {t["name"] for t in native}


def test_surface_ipc_duplicate_and_unregistered_requests_do_not_execute(browser, tmp_path):
    broker = broker_for(browser)
    bridge = browser.SurfaceBridge(tmp_path, broker)
    seen = broker.observe()
    request = {
        "id": "a" * 32,
        "op": "act",
        "args": {"ticket": seen["ticket"], "action_id": seen["actions"][0]["id"]},
    }
    assert bridge.submit(request)["ok"] is True
    assert bridge.submit(request)["ok"] is False
    assert broker.effects == 1
    for op in ("evaluate", "navigate", "close_all", "tabs", "send", "delete"):
        assert bridge.submit({"id": "b" * 32, "op": op, "args": {}})["ok"] is False
    assert broker.effects == 1
    bridge.close()


def test_remote_surface_roundtrip_has_no_network_or_raw_target_arguments(
    browser, tmp_path, monkeypatch
):
    import sys

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts/cold-bridge"))
    remote_module = importlib.import_module("browser_surface")
    broker = broker_for(browser)
    bridge = browser.SurfaceBridge(tmp_path, broker).start()
    monkeypatch.setenv("BROWSER_SURFACE_DIR", str(tmp_path))
    try:
        remote = remote_module.RemoteSurface()
        seen = remote.observe()
        action = seen["actions"][0]
        assert remote.fresh(seen, action)
        remote.act(action, seen)
        remote.settle(action)
        assert remote.check_goal()["passed"] is False
        assert broker.effects == 1
        tampered = {**action, "selector": "body"}
        with pytest.raises(ValueError, match="offered"):
            remote.act(tampered, seen)
    finally:
        bridge.close()
        sys.modules.pop("browser_surface", None)


def test_draft_http_server_does_not_expose_oracle_or_allow_send_delete(browser):
    import urllib.error
    import urllib.request

    with browser.DraftServer(browser.case_contract(0)) as server:
        html = urllib.request.urlopen(server.url).read().decode()
        assert "Digest settings" in html and "Saved draft receipt" in html
        assert "expected" not in html and "check_goal" not in html
        for path in ("oracle", "check_goal", "send", "delete"):
            request = urllib.request.Request(server.url + path, data=b"{}", method="POST")
            with pytest.raises(urllib.error.HTTPError):
                urllib.request.urlopen(request)
        assert server.state.snapshot()["save_attempts"] == 0


def test_idle_health_needs_explicit_headless_config_and_live_humanize_after_open(
    browser, monkeypatch, tmp_path
):
    import io
    import plistlib

    idle = {"ok": True, "browserRunning": False, "humanize": None}
    monkeypatch.setattr(
        browser.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(json.dumps(idle).encode())
    )
    with pytest.raises(RuntimeError, match="headless"):
        browser.check_camofox()
    config = tmp_path / "service.plist"
    config.write_bytes(
        plistlib.dumps(
            {"EnvironmentVariables": {"CAMOFOX_INTERACTIVE": "off", "PRIVATE_KEY": "do_not_return"}}
        )
    )
    result = browser.check_camofox(headless_config=config)
    assert "do_not_return" not in json.dumps(result)
    assert result["headless_evidence"]["interactive"] == "off"
    unhumanized = {"passed": False, "problems": ["humanized_pointer_not_observed"]}
    with pytest.raises(RuntimeError, match="humanize"):
        browser.check_camofox(
            headless_config=config,
            require_running=True,
            runtime=lambda base, session: unhumanized,
        )


def test_surface_response_parent_replacement_cannot_write_outside_owned_ipc(browser, tmp_path):
    import time

    root, outside = tmp_path / "ipc", tmp_path / "outside"
    outside.mkdir()
    bridge = browser.SurfaceBridge(root, broker_for(browser))
    original = root / "original-responses"
    (root / "responses").rename(original)
    if WINDOWS:
        make_junction(root / "responses", outside)
    else:
        (root / "responses").symlink_to(outside, target_is_directory=True)
    identifier = "c" * 32
    (root / "requests" / (identifier + ".json")).write_text(
        json.dumps({"id": identifier, "op": "observe", "args": {}}), newline="\n"
    )
    bridge.start()
    deadline = time.monotonic() + 2
    try:
        while not (original / (identifier + ".json")).exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert list(outside.iterdir()) == []
        assert (original / (identifier + ".json")).is_file()
    finally:
        bridge.close()


class _Actor:
    def __init__(self):
        self.started = self.closed = 0

    def start(self):
        self.started += 1
        return self

    def close(self):
        self.closed += 1


def test_handshake_answers_before_slow_preparation_and_unknown_methods_do_not_exit(
    browser, tmp_path
):
    import io
    import threading
    import time

    release = threading.Event()
    actor = _Actor()

    class Session:
        optional, live, directory = False, False, tmp_path
        events = []

        def __init__(self):
            self.actor = actor
            self.broker = broker_for(browser)

    def prepare():
        release.wait(5)
        session = Session()
        session.actor.start()
        return session

    class Recorder(io.StringIO):
        def __init__(self):
            super().__init__()
            self.times = []

        def flush(self):
            self.times.append(time.monotonic())

    pending = browser.PendingSession(tmp_path, optional=False, live=False, prepare=prepare)
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "server/discover"},
        {"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "check_goal"}},
    ]
    released = {}

    def open_gate():
        released["at"] = time.monotonic()
        release.set()

    threading.Timer(0.5, open_gate).start()
    output = Recorder()
    stream = io.StringIO("".join(json.dumps(r) + "\n" for r in requests))
    browser.serve(pending, stream, output)
    rows = [json.loads(line) for line in output.getvalue().splitlines()]
    assert rows[0]["error"]["code"] == -32601
    assert rows[1]["result"]["serverInfo"]["name"] == "browser-cold-eval"
    assert [t["name"] for t in rows[2]["result"]["tools"]] == [
        t["name"] for t in browser.tools(False)
    ]
    assert rows[3]["result"]["structuredContent"]["passed"] is False
    assert all(moment < released["at"] for moment in output.times[:3])
    assert output.times[3] >= released["at"]
    # A pending session leaves cleanup ordering (evidence first) to its caller.
    assert actor.started == 1 and actor.closed == 0


def test_failed_preparation_is_returned_as_a_tool_error_without_retry(browser, tmp_path):
    import io

    def prepare():
        raise RuntimeError("camofox_runtime_not_confirmed:browser_process_not_headless")

    pending = browser.PendingSession(tmp_path, optional=False, live=False, prepare=prepare)
    call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "observe"}}
    output = io.StringIO()
    browser.serve(pending, io.StringIO(json.dumps(call) + "\n"), output)
    result = json.loads(output.getvalue())["result"]
    assert result["isError"] is True
    body = json.loads(result["content"][0]["text"])
    assert "session_preparation_failed" in body["error"] and body["automatic_retry"] is False
