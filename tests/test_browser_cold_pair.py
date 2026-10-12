"""Browser cold pair runner: retained evidence, scoped live opt-in, owned-tab cleanup."""

import importlib
import io
import json
from pathlib import Path

import pytest


@pytest.fixture
def pair(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "benchmarks"))
    return importlib.import_module("browser_cold_pair")


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_live_inference_is_only_offered_to_the_optional_arm(pair, tmp_path):
    common = dict(
        wheel=tmp_path / "w.whl",
        variant=0,
        headless_config=None,
        session_seconds=600,
        credential=tmp_path / "key",
    )
    native = pair.serve_arguments(tmp_path / "n", "native", **common)
    optional = pair.serve_arguments(tmp_path / "o", "optional", **common)
    assert "--live" not in native and "--credential-file" not in native
    assert optional[-3:] == ["--live", "--credential-file", str(tmp_path / "key")]
    assert native[native.index("--session-seconds") + 1] == "600"


def test_terminated_serve_falls_back_to_durable_mirrors(pair, tmp_path):
    write(tmp_path / "session-progress.json", {"events": [{"tool": "act"}] * 3, "effects": 3})
    check = {"passed": False, "problems": ["projects"], "save_attempts": 1}
    write(tmp_path / "backend-live.json", {"backend": {"save_attempts": 1}, "check": check})
    collected = pair.collect(tmp_path)
    assert collected["serve_finalized"] is False
    assert collected["independent_check"] == check and collected["effects"] == 3
    assert collected["route"] == "direct" and collected["tool_counts"] == {"act": 3}


def test_finalized_session_uses_final_check_and_detects_authored_scripts(pair, tmp_path):
    write(
        tmp_path / "session-events.json",
        {"events": [], "effects": 0, "independent_check": {"passed": False}},
    )
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "task.py").write_text("workflow = None\n", encoding="utf-8")
    write(tmp_path / "script-execution.json", {"route": "caller_authored_jev"})
    collected = pair.collect(tmp_path)
    assert collected["serve_finalized"] is True and collected["route"] == "caller_authored_jev"
    assert [row["path"] for row in collected["authored_python"]] == ["task.py"]


def test_runner_closes_only_its_recorded_tab_when_left_open(pair, monkeypatch, tmp_path):
    write(tmp_path / "owned-tab.json", {"session": "general", "tab": "mine", "owned": True})
    calls = []

    def urlopen(request, timeout):
        url = request if isinstance(request, str) else request.full_url
        method = "GET" if isinstance(request, str) else request.get_method()
        calls.append((method, url))
        if method == "GET":
            body = {"tabs": [{"tabId": "mine"}, {"tabId": "someone-else"}]}
            return io.BytesIO(json.dumps(body).encode())
        return io.BytesIO(b"{}")

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    result = pair.close_leftover_owned_tab(tmp_path, base="http://127.0.0.1:9378")
    assert result["closed_by_runner"] is True
    assert [c for c in calls if c[0] == "DELETE"] == [("DELETE", "http://127.0.0.1:9378/tabs/mine")]
    write(tmp_path / "owned-tab.json", {"session": "general", "tab": "gone", "owned": True})
    calls.clear()
    assert (
        pair.close_leftover_owned_tab(tmp_path, base="http://127.0.0.1:9378")["left_open"] is False
    )
    assert all(method == "GET" for method, _ in calls)
    write(tmp_path / "owned-tab.json", {"session": "general", "tab": "x", "owned": False})
    assert pair.close_leftover_owned_tab(tmp_path)["owned_tab_recorded"] is False


def test_backend_truth_is_mirrored_on_every_save_attempt(pair):
    import browser_cold

    state = browser_cold.DraftState(browser_cold.case_contract(0))
    seen = []
    state.on_change = lambda: seen.append(state.snapshot()["save_attempts"])
    with pytest.raises(ValueError):
        state.save({"title": "only"})
    draft = {**state.expected()}
    state.save(draft)
    assert seen == [1, 2] and state.check_goal()["passed"] is False
