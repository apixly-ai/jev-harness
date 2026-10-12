"""Cold shell/script isolation seam; only the opt-in canary starts Docker."""

import importlib
import json
import os
from pathlib import Path

import pytest
from platform_support import broaden_access, make_junction, make_symlink, windows_only

from apixly_jev_harness import _secure_fs


@pytest.fixture
def cold(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "benchmarks"))
    return importlib.import_module("cold_authoring")


def test_actor_mounts_only_public_runtime_corpus_and_owned_work(cold, tmp_path):
    corpus, work, runtime = (tmp_path / x for x in ("corpus", "work", "runtime"))
    for path in (corpus, work, runtime):
        path.mkdir()
    actor = cold.DockerActor(corpus, work, runtime=runtime)
    command = actor.command("scope-canary")
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command and "--cap-drop=ALL" in command
    assert not any(value.startswith("HOME=") for value in command)
    mounts = [command[i + 1] for i, value in enumerate(command) if value == "--mount"]
    assert len(mounts) == 3
    assert any("target=/corpus,readonly" in value for value in mounts)
    assert any("target=/runtime,readonly" in value for value in mounts)
    assert not any(
        "oracle" in value or "credential" in value or ".codex" in value for value in mounts
    )


def test_only_optional_arm_exposes_script_execution(cold):
    native, optional = cold.tools(False), cold.tools(True)
    assert [row["name"] for row in native] == ["shell"]
    assert [row["name"] for row in optional] == ["shell", "run_script"]
    assert optional[1]["inputSchema"]["required"] == ["script"]
    assert "already registered" not in optional[1]["description"]


def test_script_snapshot_is_owned_regular_file_and_source_exact(cold, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    script = work / "task.py"
    body = "workflow = None\n"
    script.write_text(body, encoding="utf-8", newline="\n")
    frozen = cold.freeze_script(work, "task.py", tmp_path / "frozen")
    script.write_text('workflow = "changed"\n', encoding="utf-8", newline="\n")
    assert frozen["path"].read_text() == body
    assert len(frozen["sha256"]) == 64
    assert frozen["static_check"] == "syntax_and_export_ok"


@pytest.mark.parametrize("reference", ["../oracle.py", "/controller/oracle.py", "/work/task.py"])
def test_script_reference_cannot_escape_work(cold, tmp_path, reference):
    with pytest.raises(ValueError, match="script_reference"):
        cold.freeze_script(tmp_path, reference, tmp_path / "frozen")


def test_script_symlink_is_rejected_before_loading(cold, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("workflow = None\n", encoding="utf-8", newline="\n")
    make_symlink(work / "task.py", outside)
    with pytest.raises(ValueError, match="script_reference"):
        cold.freeze_script(work, "task.py", tmp_path / "frozen")


def test_script_parent_symlink_is_rejected_even_when_target_is_owned(cold, tmp_path):
    work = tmp_path / "work"
    (work / "owned").mkdir(parents=True)
    (work / "owned/task.py").write_text("workflow = None\n", encoding="utf-8", newline="\n")
    make_symlink(work / "alias", work / "owned", directory=True)
    with pytest.raises((ValueError, OSError)):
        cold.freeze_script(work, "alias/task.py", tmp_path / "frozen")


@windows_only
def test_script_parent_junction_is_rejected_even_when_target_is_owned(cold, tmp_path):
    work = tmp_path / "work"
    (work / "owned").mkdir(parents=True)
    (work / "owned/task.py").write_text("workflow = None\n", encoding="utf-8", newline="\n")
    make_junction(work / "alias", work / "owned")
    with pytest.raises(ValueError, match="script_reference"):
        cold.freeze_script(work, "alias/task.py", tmp_path / "frozen")
    assert not (tmp_path / "frozen").exists()


def test_bridge_calls_fake_provider_once_and_rejects_duplicate(cold, tmp_path):
    calls = []
    provider = cold.FakeProvider(on_request=lambda body: calls.append(body))
    bridge = cold.FileBridge(tmp_path, provider, max_requests=2, timeout_seconds=5)
    body = {
        "model": "jev-1.13.0",
        "state": {},
        "questions": {
            "q": {"type": "choice", "instructions": "Synthetic", "criteria": {"a": "A", "b": "B"}}
        },
    }
    request = {"id": "a" * 32, "body": body}
    first = bridge.submit(request)
    second = bridge.submit(request)
    assert first["status"] == 200
    assert second["status"] == 409
    assert len(calls) == 1
    assert bridge.summary()["actual_model_usage"]["requests"] == 0
    assert bridge.summary()["mock_submissions"] == 1


def test_bridge_budget_stops_before_provider_and_never_turns_unknown_into_zero(cold, tmp_path):
    provider = cold.FakeProvider(fail=True)
    bridge = cold.FileBridge(tmp_path, provider, max_requests=1, timeout_seconds=5)
    body = {
        "model": "jev-1.13.0",
        "state": {},
        "questions": {"q": {"type": "noul", "instructions": "Synthetic"}},
    }
    assert bridge.submit({"id": "a" * 32, "body": body})["status"] == 520
    assert bridge.submit({"id": "b" * 32, "body": body})["status"] == 429
    summary = bridge.summary()
    assert summary["unknown_mock_usage_attempts"] == 1
    assert summary["reported_mock_usage"] is None
    assert summary["actual_model_usage"]["requests"] == 0


def test_live_provider_is_not_enabled_by_fake_replay(cold, tmp_path):
    class Billable:
        mode = "live"

    with pytest.raises(ValueError, match="live_provider_not_enabled"):
        cold.FileBridge(tmp_path, Billable())


def test_bridge_rejects_endpoint_headers_and_oversized_or_untyped_payload(cold, tmp_path):
    bridge = cold.FileBridge(tmp_path, cold.FakeProvider())
    for request in (
        {"id": "a" * 32, "body": {}, "url": "https://outside.invalid"},
        {"id": "b" * 32, "body": {"state": "x" * 70000}},
    ):
        assert bridge.submit(request)["status"] == 400
    assert bridge.summary()["mock_submissions"] == 0


def test_neutral_prompt_contains_goal_scope_and_artifact_not_route_rule(cold):
    prompt = cold.actor_prompt("Investigate the current source", {"proof": '"scenario":'})
    assert (
        "Investigate the current source" in prompt
        and "/corpus" in prompt
        and "/work/report.json" in prompt
    )
    assert (
        "prefer" not in prompt.lower() and "Jev" not in prompt and "harness" not in prompt.lower()
    )


def test_prompt_explicitly_defines_flat_envelope_label_enum_and_quote_identity(cold):
    prompt = cold.actor_prompt(
        "Investigate the source", {"implementation": "def ", "proof": '"scenario":'}
    )
    assert '{"records": [' in prompt
    assert 'label must be exactly one of ["implementation", "proof"]' in prompt
    for key in ('"source"', '"text"', '"offset"', '"end"', '"total"', '"sha256"'):
        assert key in prompt
    assert "Unicode characters" in prompt and "end-exclusive" in prompt
    assert "complete original UTF-8 source" in prompt
    assert (
        "Jev" not in prompt and "harness" not in prompt.lower() and "prefer" not in prompt.lower()
    )


def _quoted_sources(case):
    import hashlib

    rows = {}
    root = Path(case["source_directory"])
    for label, relative in case["expected"].items():
        path = root / relative
        if not path.exists():
            continue
        body = path.read_text()
        rows[label] = {
            "label": "Human description for " + label,
            "source": "workspace:" + relative,
            "text": body,
            "offset": 0,
            "end": len(body),
            "total": len(body),
            "sha256": hashlib.sha256(body.encode()).hexdigest(),
        }
    return rows


def test_grouped_posthoc_adapter_changes_only_label_from_explicit_goal_group(cold):
    import copy

    row = {
        "label": "Human description",
        "source": "workspace:a.py",
        "text": "quoted",
        "offset": 2,
        "end": 8,
        "total": 10,
        "sha256": "a" * 64,
        "purpose": "unchanged extra field",
    }
    original = {"implementation": [row], "summary": "unchanged"}
    before = copy.deepcopy(original)
    result = cold.canonicalize_report(original, ["implementation", "proof"])
    assert original == before
    assert result["report"]["records"] == [{**row, "label": "implementation"}]
    assert result["adapter"]["mode"] == "posthoc_shape_adapter"
    assert result["adapter"]["source_of_labels"] == "explicit_goal_category_groups"
    assert result["adapter"]["missing_groups"] == ["proof"]


def test_adapter_does_not_guess_flat_labels_from_source_or_repair_conflicting_groups(cold):
    row = {
        "label": "human description",
        "source": "workspace:src/worker.py",
        "text": "quote",
        "offset": 0,
        "end": 5,
        "total": 5,
        "sha256": "a" * 64,
    }
    result = cold.canonicalize_report({"records": [row]}, ["implementation", "proof"])
    assert result["report"]["records"][0]["label"] == "human description"
    with pytest.raises(ValueError, match="conflicting_group_label"):
        cold.canonicalize_report(
            {"implementation": [{**row, "label": "proof"}]}, ["implementation", "proof"]
        )


def test_adapter_rejects_mixed_envelopes_and_unknown_evidence_groups(cold):
    row = {"label": "description", "source": "workspace:a.py", "text": "quote"}
    with pytest.raises(ValueError, match="ambiguous_report_shape"):
        cold.canonicalize_report({"records": [], "implementation": [row]}, ["implementation"])
    with pytest.raises(ValueError, match="unknown_evidence_group"):
        cold.canonicalize_report(
            {"implementation": [row], "other_category": [row]}, ["implementation"]
        )


def test_posthoc_score_never_overwrites_the_original_or_prior_normalized_artifact(cold, tmp_path):
    from adoption_cases import fixture

    case = fixture(tmp_path / "corpus", "short", 0)
    raw = tmp_path / "raw.json"
    raw.write_text(
        json.dumps({label: [row] for label, row in _quoted_sources(case).items()}), newline="\n"
    )
    original = raw.read_bytes()
    with pytest.raises(FileExistsError):
        cold.score_report(case, raw, normalized_output=raw)
    assert raw.read_bytes() == original


@pytest.mark.parametrize("variant", [0, 1])
def test_controller_posthoc_score_preserves_raw_failure_and_scores_unchanged_facts(
    cold, tmp_path, variant
):
    from adoption_cases import fixture

    case = fixture(tmp_path / "corpus", "medium", variant)
    grouped = {label: [row] for label, row in _quoted_sources(case).items()}
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps(grouped), encoding="utf-8", newline="\n")
    before = raw.read_bytes()
    result = cold.score_report(case, raw, normalized_output=tmp_path / "normalized.json")
    assert result["raw_format"]["passed"] is False
    assert result["raw_independent_check"]["passed"] is False
    assert result["normalized_independent_check"]["passed"] is True
    assert result["adapter"]["mode"] == "posthoc_shape_adapter"
    assert raw.read_bytes() == before
    normalized = json.loads((tmp_path / "normalized.json").read_text())["records"]
    for row in normalized:
        original = grouped[row["label"]][0]
        assert {k: v for k, v in row.items() if k != "label"} == {
            k: v for k, v in original.items() if k != "label"
        }


@pytest.mark.parametrize(
    "damage", ["quote", "digest", "span", "old_version", "header_only", "missing"]
)
def test_posthoc_adapter_never_repairs_unsupported_or_incomplete_facts(cold, tmp_path, damage):
    from adoption_cases import fixture

    case = fixture(tmp_path / "corpus", "missing" if damage == "missing" else "medium", 0)
    grouped = {label: [row] for label, row in _quoted_sources(case).items()}
    row = grouped["implementation"][0]
    if damage == "quote":
        row["text"] += " unsupported claim"
    elif damage == "digest":
        row["sha256"] = "0" * 64
    elif damage == "span":
        row["end"] -= 1
    elif damage == "old_version":
        old = Path(case["source_directory"]) / "tests/results/previous.json"
        body = old.read_text()
        import hashlib

        grouped["reproduction"][0].update(
            source="workspace:tests/results/previous.json",
            text=body,
            offset=0,
            end=len(body),
            total=len(body),
            sha256=hashlib.sha256(body.encode()).hexdigest(),
        )
    elif damage == "header_only":
        row.update(text="def submit(", offset=0, end=len("def submit("))
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps(grouped), encoding="utf-8", newline="\n")
    result = cold.score_report(case, raw, normalized_output=tmp_path / "normalized.json")
    assert result["normalized_independent_check"]["passed"] is False


def test_output_directory_is_exclusive_before_build_or_docker(cold, tmp_path, monkeypatch):
    output = tmp_path / "owner"
    output.mkdir()

    def forbidden(*a, **k):
        raise AssertionError("Existing output must not execute setup")

    monkeypatch.setattr(cold, "build_runtime", forbidden)
    with pytest.raises(FileExistsError):
        cold.canary(output, None)


def test_native_sdk_provider_keeps_key_on_host_and_records_actual_response_usage(cold, tmp_path):
    import httpx

    key = private_key(tmp_path / "host-test-key")
    captured = []

    def respond(request):
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "model": "jev-test-double",
                "answers": {"q": {"type": "noul", "noul": 1.0}},
                "usage": {"input_tokens": 9, "output_tokens": 2},
            },
        )

    provider = cold.NativeProvider(key, transport=httpx.MockTransport(respond))
    bridge = cold.FileBridge(tmp_path / "ipc", provider, allow_live=True)
    try:
        result = bridge.submit(
            {
                "id": "a" * 32,
                "body": {
                    "model": "jev-1.13.0",
                    "state": {},
                    "questions": {"q": {"type": "noul", "instructions": "Synthetic"}},
                },
            }
        )
        assert result["status"] == 200
        assert "synthetic-private-host-key" not in json.dumps(result)
        assert captured[0].headers["authorization"] == "Bearer synthetic-private-host-key"
        usage = bridge.summary()["actual_model_usage"]
        assert usage["requests"] == 1 and usage["models"]["jev-test-double"] == {
            "input_tokens": 9,
            "output_tokens": 2,
        }
    finally:
        bridge.close()


def test_native_sdk_retry_is_not_a_second_physical_submission(cold, tmp_path):
    import httpx

    key = private_key(tmp_path / "host-test-key")
    calls = []
    provider = cold.NativeProvider(
        key,
        transport=httpx.MockTransport(
            lambda request: (
                calls.append(1) or httpx.Response(503, json={"error": "synthetic outage"})
            )
        ),
    )
    bridge = cold.FileBridge(tmp_path / "ipc", provider, allow_live=True)
    try:
        response = bridge.submit(
            {
                "id": "a" * 32,
                "body": {
                    "model": "jev-1.13.0",
                    "state": {},
                    "questions": {"q": {"type": "noul", "instructions": "Synthetic"}},
                },
            }
        )
        assert response["status"] == 520
        assert calls == [1]
        summary = bridge.summary()
        assert summary["actual_model_usage"]["requests"] == 1
        assert summary["actual_model_usage"]["usage_complete"] is False
        assert summary["actual_model_usage"]["input_tokens"] is None
        assert summary["native_sdk_attempts"] == 2
    finally:
        bridge.close()


def test_live_tool_metadata_describes_jev_loop_without_fake_claim(cold):
    live = cold.tools(True, live=True)[1]
    assert "Jev Harness" in live["description"] and "registered tools" in live["description"]
    assert "independent" in live["description"] and "fake" not in live["description"].lower()
    assert "offline fake" in cold.tools(True)[1]["description"]


@pytest.mark.parametrize(
    "arguments",
    [
        ["--arm", "optional", "--live"],
        ["--arm", "optional", "--credential-file", "private-key"],
        ["--arm", "native", "--live", "--credential-file", "private-key"],
    ],
)
def test_live_cli_requires_explicit_host_only_opt_in_before_setup(cold, tmp_path, arguments):
    output = tmp_path / "owner"
    with pytest.raises(SystemExit) as error:
        cold.main(["serve", "--directory", str(output), *arguments])
    assert error.value.code == 2
    assert not output.exists()


def test_cold_execution_uses_public_mcp_and_retains_artifact_and_original_quotes(
    cold, tmp_path, monkeypatch
):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    case = {
        "goal": "Read this source",
        "inputs": {"root": str(corpus), "queries": {}, "requirements": {}},
    }
    session = cold.ColdSession(tmp_path, case, tmp_path / "runtime")
    (session.work / "task.py").write_text("workflow = None\n", encoding="utf-8", newline="\n")
    terminal = {
        "complete": True,
        "status": "done",
        "artifact": {"path": "/work/report.json", "matches_records": True},
        "report": {"records": [{"source": "workspace:package.json", "text": "original"}]},
    }
    calls = []

    def invoke(self, argv, **kwargs):
        calls.append((argv, kwargs))
        return {"exit_code": 0, "stdout": json.dumps({"result": {"structuredContent": terminal}})}

    monkeypatch.setattr(cold.DockerActor, "start", lambda self: self)
    monkeypatch.setattr(cold.DockerActor, "close", lambda self: None)
    monkeypatch.setattr(cold.DockerActor, "invoke", invoke)
    result = session.run_script("task.py")
    assert "apixly_jev_harness.mcp" in calls[0][0]
    assert json.loads(calls[0][1]["input_text"])["params"]["name"] == "run_task"
    assert result["terminal"]["artifact"] == terminal["artifact"]
    assert result["terminal"]["report"]["records"][0]["text"] == "original"
    assert result["bridge"]["actual_model_usage"]["requests"] == 0


def test_worker_timeout_is_preserved_as_terminal_unknown_and_never_retried(
    cold, tmp_path, monkeypatch
):
    import subprocess

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    case = {
        "goal": "Read this source",
        "inputs": {"root": str(corpus), "queries": {}, "requirements": {}},
    }
    session = cold.ColdSession(tmp_path, case, tmp_path / "runtime")
    (session.work / "task.py").write_text("workflow = None\n", encoding="utf-8", newline="\n")
    calls = []

    def invoke(self, argv, **kwargs):
        calls.append(1)
        raise subprocess.TimeoutExpired("worker", 100)

    monkeypatch.setattr(cold.DockerActor, "start", lambda self: self)
    monkeypatch.setattr(cold.DockerActor, "close", lambda self: None)
    monkeypatch.setattr(cold.DockerActor, "invoke", invoke)
    result = session.run_script("task.py")
    assert result["terminal"] == {
        "status": "execution_uncertain",
        "complete": False,
        "automatic_retry": False,
    }
    assert result["process"]["error_type"] == "TimeoutExpired"
    assert (tmp_path / "script-execution.json").is_file()
    with pytest.raises(ValueError, match="already_attempted"):
        session.run_script("task.py")
    assert calls == [1]


def test_caller_can_fix_syntax_before_the_single_execution_is_consumed(cold, tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    case = {
        "goal": "Read this source",
        "inputs": {"root": str(corpus), "queries": {}, "requirements": {}},
    }
    session = cold.ColdSession(tmp_path, case, tmp_path / "runtime")
    (session.work / "task.py").write_text("workflow = (\n")
    bad = session.run_script("/work/task.py")
    assert bad["phase"] == "script_preflight" and bad["execution_attempted"] is False
    assert session.executions == 0
    assert session.events[-1]["phase"] == "script_preflight"
    (session.work / "task.py").write_text("workflow = None\n", encoding="utf-8", newline="\n")
    monkeypatch.setattr(cold.DockerActor, "start", lambda self: self)
    monkeypatch.setattr(cold.DockerActor, "close", lambda self: None)
    monkeypatch.setattr(
        cold.DockerActor,
        "invoke",
        lambda *a, **k: {
            "exit_code": 0,
            "stdout": json.dumps(
                {"result": {"structuredContent": {"complete": False, "status": "needs_review"}}}
            ),
        },
    )
    result = session.run_script("/work/task.py")
    assert result["terminal"]["status"] == "needs_review" and session.executions == 1


def test_host_absolute_reference_is_preflight_failure_without_consuming_execution(cold, tmp_path):
    case = {
        "goal": "Read this source",
        "inputs": {"root": str(tmp_path), "queries": {}, "requirements": {}},
    }
    session = cold.ColdSession(tmp_path, case, tmp_path / "runtime")
    result = session.run_script("/controller/secret.py")
    assert result["execution_attempted"] is False and session.executions == 0
    assert result["model_calls"] == 0


def private_key(path):
    fd = _secure_fs.open_private_file(path, "x")
    os.write(fd, b"synthetic-private-host-key")
    os.close(fd)
    return path


def test_native_provider_refuses_a_credential_readable_by_others(cold, tmp_path):
    key = private_key(tmp_path / "host-test-key")
    broaden_access(key)
    with pytest.raises(Exception) as raised:
        cold.NativeProvider(key, transport=object())
    assert "credential" in str(raised.value) or "permission" in str(raised.value)


def test_wsl_daemon_keeps_isolation_flags_and_maps_drive_paths(cold, tmp_path, monkeypatch):
    monkeypatch.setattr(cold, "DOCKER", {"prefix": ["docker"], "wsl_distro": None})
    monkeypatch.setattr(cold.Path, "resolve", lambda self, strict=False: self)
    direct = cold.DockerActor(tmp_path / "corpus", tmp_path / "work").command("n")
    cold.configure_docker("Ubuntu")
    actor = cold.DockerActor(cold.Path("C:/x/corpus"), cold.Path("C:/x/work"))
    routed = actor.command("n")
    assert routed[:7] == ["wsl.exe", "-d", "Ubuntu", "-u", "root", "--", "docker"]
    assert routed[7:].count("--network") == 1 and "none" in routed
    assert "type=bind,source=/mnt/c/x/corpus,target=/corpus,readonly" in routed
    assert "type=bind,source=/mnt/c/x/work,target=/work" in routed
    assert [x for x in routed[7:] if not x.startswith("type=bind")] == [
        x for x in direct[1:] if not x.startswith("type=bind")
    ]
    for bad in ("Ubuntu; rm", "", 3):
        with pytest.raises(ValueError):
            cold.configure_docker(bad)


def test_container_processes_never_inherit_the_mcp_stdin(cold, tmp_path, monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(kwargs)
        return cold.subprocess.CompletedProcess(
            argv, 0, stdout=b"cid" if "text" not in kwargs else "cid", stderr=b""
        )

    monkeypatch.setattr(cold.subprocess, "run", fake_run)
    actor = cold.DockerActor(tmp_path, tmp_path).start()
    actor.shell("true")
    actor.invoke(["cat"], input_text="payload")
    actor.close()
    assert calls[0]["stdin"] is cold.subprocess.DEVNULL
    assert calls[1]["input"] == b"" and calls[2]["input"] == b"payload"
    assert calls[3]["stdin"] is cold.subprocess.DEVNULL
