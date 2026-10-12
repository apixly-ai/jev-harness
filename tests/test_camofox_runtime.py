"""Camofox runtime evidence: configuration is never proof; process and pointer probes are."""

import importlib
import io
import json
from pathlib import Path

import pytest


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "benchmarks"))
    return importlib.import_module("camofox_runtime")


@pytest.fixture
def browser(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "benchmarks"))
    return importlib.import_module("browser_cold")


PROFILE = "profile-c4c87334f320ad129c66a546774327c78f40e7e00f03e4e194159af2b5177949"


def table(*, headless=True, profile=PROFILE, extra=()):
    flag = ["-headless"] if headless else []
    root = ["camoufox.exe", "-no-remote", *flag, "-profile", "C:/p/" + profile, "-juggler-pipe"]
    return [
        {"pid": 10, "ppid": 1, "name": "node.exe", "argv": ["node", "server.js"]},
        {"pid": 11, "ppid": 10, "name": "camoufox.exe", "argv": root},
        {"pid": 12, "ppid": 11, "name": "camoufox.exe", "argv": root},
        {"pid": 13, "ppid": 12, "name": "camoufox.exe", "argv": ["camoufox.exe", "-contentproc"]},
        {"pid": 99, "ppid": 1, "name": "camoufox.exe", "argv": ["camoufox.exe", "-profile", "x"]},
        *extra,
    ]


def evidence(runtime, rows, *, windows=frozenset(), version="2.4.8"):
    return runtime.headless_evidence(
        "http://127.0.0.1:9378",
        "camofox-general",
        service_version=version,
        pid_of=lambda port: 10 if port == 9378 else None,
        rows=rows,
        windows=lambda pids: set(windows) & pids,
    )


def test_profile_naming_matches_known_service_version_only(runtime):
    assert (
        runtime.profile_directory_name("camofox-general", platform="win32", service_version="2.4.8")
        == PROFILE
    )
    assert (
        runtime.profile_directory_name("camofox-general", platform="linux", service_version="2.4.1")
        == "camofox-general"
    )
    assert runtime.profile_directory_name("camofox-general", service_version="9.0.0") is None


def test_headless_process_tree_for_the_session_profile_passes(runtime):
    packet = evidence(runtime, table())
    assert packet["passed"] is True
    assert packet["browser_processes"] == 2 and packet["process_tree"] == 3
    assert packet["session_profile_process"] is True and packet["visible_windows"] == 0


@pytest.mark.parametrize(
    "rows, windows, problem",
    [
        (table(headless=False), (), "browser_process_not_headless"),
        (table(), (12,), "visible_browser_window"),
        (table(profile="profile-other"), (), "session_profile_process_unobserved"),
        (
            [{"pid": 10, "ppid": 1, "name": "node", "argv": ["node"]}],
            (),
            "browser_process_unobserved",
        ),
    ],
)
def test_headed_windowed_or_foreign_profile_processes_fail(runtime, rows, windows, problem):
    packet = evidence(runtime, rows, windows=windows)
    assert packet["passed"] is False and problem in packet["problems"]


def test_unknown_service_version_requires_every_service_browser_headless(runtime):
    packet = evidence(runtime, table(profile="unknown-naming"), version="3.0.0")
    assert packet["passed"] is True
    assert packet["session_mapping"] == "unverified_all_service_browsers"
    unobserved = runtime.headless_evidence(
        "http://127.0.0.1:9378", "camofox-general", pid_of=lambda port: None, rows=table()
    )
    assert "service_listener_unobserved" in unobserved["problems"]


def test_trajectory_distinguishes_humanized_from_single_jump(runtime):
    humanized = [[1000 + 12 * i, 100 + 5 * i, 3 * i] for i in range(40)]
    assert runtime.trajectory_verdict(humanized)["passed"] is True
    assert runtime.trajectory_verdict([[1186, 680, 430]])["passed"] is False
    assert runtime.trajectory_verdict([[1, 5, 5]] * 30)["passed"] is False
    assert runtime.trajectory_verdict([])["passed"] is False


class ProbePage:
    instances = []

    def __init__(self, session, url=None, base=None, moves=None):
        self.session, self.url, self.base = session, url, base
        self.user, self.owned, self.closed, self.clicks = "camofox-" + session, True, False, []
        self.moves = moves
        ProbePage.instances.append(self)

    def _tab(self, suffix, body):
        self.clicks.append((suffix, body))
        return {"ok": True}

    def evaluate(self, expression):
        assert expression == "document.body.dataset.moves || '[]'"
        return json.dumps(self.moves)

    def close(self):
        self.closed = True


def probe(runtime, moves, *, active=True, headless_passed=True):
    ProbePage.instances.clear()
    return runtime.runtime_evidence(
        "http://127.0.0.1:9378",
        "general",
        page_factory=lambda session, url, base: ProbePage(session, url, base, moves),
        health=lambda base: {
            "ok": True,
            "engine": "camoufox",
            "version": "2.4.8",
            "activeUserIds": ["camofox-general"] if active else [],
            "browserConnected": active,
        },
        headless=lambda base, user, service_version: {
            "passed": headless_passed,
            "problems": [] if headless_passed else ["browser_process_not_headless"],
        },
    )


def test_runtime_probe_uses_owned_tab_same_click_route_and_closes_only_it(runtime):
    packet = probe(runtime, [[1000 + 12 * i, 100 + 5 * i, 3 * i] for i in range(40)])
    page = ProbePage.instances[0]
    assert packet["passed"] is True and packet["problems"] == []
    assert page.session == "general" and page.url.startswith("http://127.0.0.1:")
    assert page.clicks == [("click", {"selector": "#pointer-probe"})]
    assert page.closed is True and packet["probe_tab_owned_and_closed"] is True


@pytest.mark.parametrize(
    "moves, active, headless_passed, problem",
    [
        ([[1186, 680, 430]], True, True, "humanized_pointer_not_observed"),
        ([[1000 + 12 * i, i, i] for i in range(40)], False, True, "session_context_not_active"),
        ([[1000 + 12 * i, i, i] for i in range(40)], True, False, "browser_process_not_headless"),
    ],
)
def test_runtime_probe_failures_are_retained(runtime, moves, active, headless_passed, problem):
    packet = probe(runtime, moves, active=active, headless_passed=headless_passed)
    assert packet["passed"] is False and problem in packet["problems"]
    assert ProbePage.instances[0].closed is True


def test_running_gate_never_accepts_configuration_as_runtime_proof(browser, monkeypatch, tmp_path):
    health = {"ok": True, "engine": "camoufox", "version": "2.4.8", "activeUserIds": []}
    monkeypatch.setattr(
        browser.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(json.dumps(health).encode())
    )
    config = tmp_path / "service.json"
    config.write_text(
        json.dumps({"EnvironmentVariables": {"CAMOFOX_HEADLESS": "true", "SECRET": "nope"}}),
        encoding="utf-8",
    )
    before = browser.check_camofox(headless_config=config)
    assert before["headless_evidence"]["kind"] == "caller_supplied_service_configuration"
    assert "nope" not in json.dumps(before)
    failing = {"passed": False, "problems": ["browser_process_not_headless"]}
    with pytest.raises(RuntimeError, match="headless"):
        browser.check_camofox(
            headless_config=config, require_running=True, runtime=lambda base, session: failing
        )
    passing = {"passed": True, "problems": [], "humanize": {"passed": True}}
    running = browser.check_camofox(
        headless_config=config, require_running=True, runtime=lambda base, session: passing
    )
    assert running["runtime_evidence"] == passing
    assert running["headless_evidence"]["kind"] == "caller_supplied_service_configuration"


def test_service_reported_negative_humanize_fails_before_opening(browser, monkeypatch, tmp_path):
    health = {"ok": True, "headless": True, "humanize": False}
    monkeypatch.setattr(
        browser.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(json.dumps(health).encode())
    )
    with pytest.raises(RuntimeError, match="humanize"):
        browser.check_camofox()


def test_tab_creation_waits_out_tabless_context_teardown_without_closing_anything(runtime):
    states = iter(
        [
            ({"activeUserIds": ["camofox-general"]}, {"tabs": []}),
            ({"activeUserIds": ["camofox-general"]}, {"tabs": []}),
            ({"activeUserIds": []}, {"tabs": []}),
        ]
    )
    calls = []
    current = {}

    def opener(url, timeout):
        calls.append(url)
        if url.endswith("/health"):
            current["health"], current["tabs"] = next(states)
            return io.BytesIO(json.dumps(current["health"]).encode())
        assert "/tabs?userId=camofox-general" in url
        return io.BytesIO(json.dumps(current["tabs"]).encode())

    ready = runtime.await_session_ready(
        "http://127.0.0.1:9378", "camofox-general", opener=opener, sleep=lambda _: None
    )
    assert ready["context_active"] is False and ready["existing_tabs"] == 0
    assert all("/tabs/" not in url for url in calls)


def test_existing_tabs_keep_context_alive_and_stuck_teardown_fails_closed(runtime):
    def alive(url, timeout):
        body = {"activeUserIds": ["camofox-general"], "tabs": [{"tabId": "other"}]}
        return io.BytesIO(json.dumps(body).encode())

    ready = runtime.await_session_ready("http://127.0.0.1:9378", "camofox-general", opener=alive)
    assert ready["existing_tabs"] == 1 and ready["waited_seconds"] == 0

    def stuck(url, timeout):
        return io.BytesIO(json.dumps({"activeUserIds": ["camofox-general"], "tabs": []}).encode())

    with pytest.raises(RuntimeError, match="teardown"):
        runtime.await_session_ready(
            "http://127.0.0.1:9378",
            "camofox-general",
            opener=stuck,
            timeout_seconds=0,
            sleep=lambda _: None,
        )
