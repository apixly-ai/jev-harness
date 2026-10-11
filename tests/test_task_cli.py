"""Offline thin-script scaffolds and one public CLI for direct/Jev MCP choices."""

import importlib.util
import json

import pytest

from apixly_jev_harness import Context, TaskScript, cli, task_cli

TOOLKITS = ("workspace", "http", "browser")


def scaffold(tmp_path, capsys, toolkit):
    target = tmp_path / f"{toolkit}.py"
    assert task_cli.main(["init-task", str(target), "--toolkit", toolkit]) == 0
    packet = json.loads(capsys.readouterr().out)
    assert packet["status"] == "created" and packet["model_calls"] == 0
    assert packet["toolkit"] == toolkit
    return target


def load(path):
    spec = importlib.util.spec_from_file_location("_scaffold_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_counter_scaffold_is_unchanged(tmp_path, capsys):
    target = tmp_path / "counter.py"
    assert task_cli.main(["init-task", str(target)]) == 0
    assert target.read_text() == task_cli.TEMPLATE
    assert "toolkit" not in json.loads(capsys.readouterr().out)


@pytest.mark.parametrize("toolkit", TOOLKITS)
def test_toolkit_scaffold_is_thin_lazy_and_static_checkable(tmp_path, capsys, monkeypatch, toolkit):
    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Template generation, import and static check must not acquire sources"
        )

    monkeypatch.setattr("apixly_jev_harness.HttpProvider", forbidden)
    monkeypatch.setattr("apixly_jev_harness.CamofoxProvider", forbidden)
    monkeypatch.setattr("apixly_jev_harness.WorkspaceTools", forbidden)
    monkeypatch.setattr("apixly_jev_harness.backend.native_run", forbidden)
    target = scaffold(tmp_path, capsys, toolkit)
    assert task_cli.main(["check-task", str(target)]) == 0
    assert json.loads(capsys.readouterr().out)["code"] == "syntax_and_export_ok"
    module = load(target)
    assert isinstance(module.workflow, TaskScript)
    assert module.workflow._task is None
    text = target.read_text()
    assert "EvidenceTask" in text and "record_checks" in text
    assert "schema prefixes" in text
    assert "observed-link" not in text and "spruce" not in text


@pytest.mark.parametrize("toolkit", TOOLKITS)
def test_toolkit_scaffold_does_not_replace_owned_script(tmp_path, capsys, toolkit):
    target = tmp_path / "task.py"
    target.write_text("caller-owned source")
    assert task_cli.main(["init-task", str(target), "--toolkit", toolkit]) == 2
    assert target.read_text() == "caller-owned source"
    assert json.loads(capsys.readouterr().out)["status"] == "failed"


def test_unknown_toolkit_is_rejected_before_creating_script(tmp_path, capsys):
    target = tmp_path / "task.py"
    assert task_cli.main(["init-task", str(target), "--toolkit", "PRIVATE_UNREGISTERED"]) == 2
    assert not target.exists()
    output = capsys.readouterr().out
    assert "PRIVATE_UNREGISTERED" not in output
    assert json.loads(output)["code"] == "invalid_command_arguments"


def test_packaged_template_is_used_before_source_checkout(tmp_path, capsys, monkeypatch):
    body = '"""Bundled schema prefixes contract."""\nworkflow = None\n'

    class Resource:
        def joinpath(self, name):
            assert name == "templates/http.py"
            return self

        def is_file(self):
            return True

        def read_text(self, encoding="utf-8"):
            return body

    monkeypatch.setattr(task_cli, "files", lambda package: Resource())
    assert scaffold(tmp_path, capsys, "http").read_text() == body


def synthetic_page():
    text = "Cause: captured source fact\nProof: recorded source check"
    return {
        "url": "https://source.test/entry",
        "title": "Source",
        "text": text,
        "links": [],
        "sections": [{"id": "section:0", "title": "Source", "start": 0, "end": len(text)}],
        "source": {"kind": "synthetic"},
        "fingerprint": "synthetic-source-fingerprint",
    }


@pytest.mark.parametrize("toolkit", TOOLKITS)
def test_thin_factory_uses_runtime_inputs_and_independently_checks_saved_artifact(
    tmp_path, capsys, monkeypatch, toolkit
):
    calls = []

    class Provider:
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))

        def capture(self):
            return synthetic_page()

    target = scaffold(tmp_path, capsys, toolkit)
    if toolkit == "workspace":
        root = tmp_path / "sources"
        root.mkdir()
        (root / "facts.txt").write_text(synthetic_page()["text"])
        location = {"root": str(root), "queries": ["captured"]}
    else:
        monkeypatch.setattr("apixly_jev_harness.HttpProvider", Provider)
        monkeypatch.setattr("apixly_jev_harness.CamofoxProvider", Provider)
        location = {"url": "https://source.test/entry", "allowed_origins": ["https://source.test"]}
        if toolkit == "browser":
            location["session"] = "owned-fixture"
    inputs = {
        **location,
        "output": str(tmp_path / "report.json"),
        "markers": {"cause": "Cause:", "proof": "Proof:"},
    }
    module = load(target)
    ctx = Context(goal="Collect required source fields", inputs=inputs, facts={})
    task = module.workflow.materialize(ctx)
    assert task.verify(ctx, task.observe(ctx)) is False
    if toolkit == "workspace":
        pack = task.toolkits[0]
        listing = pack.list_files()
        pack.read_file(listing["files"][0]["id"])
    else:
        assert calls[0][1]["allowed_origins"] == inputs["allowed_origins"]
        if toolkit == "browser":
            assert calls[0][1]["session"] == "owned-fixture"
        assert module.workflow.materialize(ctx) is task and len(calls) == 1
    ref = task.store.references()[0]["ref"]
    passage = {"ref": ref, "offset": 0, "limit": 1200}
    task.record_evidence(passage, "cause")
    task.save_report()
    assert task.verify(ctx, task.observe(ctx)) is False
    task.record_evidence(passage, "proof")
    task.save_report()
    assert task.verify(ctx, task.observe(ctx)) is True
    assert set(task.artifact_receipt()) >= {"path", "sha256"}
    for pack in task.toolkits:
        if hasattr(pack, "close"):
            pack.close()


@pytest.mark.parametrize("toolkit", TOOLKITS)
def test_invalid_marker_contract_fails_before_source_acquisition(
    tmp_path, capsys, monkeypatch, toolkit
):
    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid marker contract must fail before source I/O")

    target = scaffold(tmp_path, capsys, toolkit)
    monkeypatch.setattr("apixly_jev_harness.HttpProvider", forbidden)
    monkeypatch.setattr("apixly_jev_harness.CamofoxProvider", forbidden)
    monkeypatch.setattr("apixly_jev_harness.WorkspaceTools", forbidden)
    module = load(target)
    with pytest.raises(ValueError, match="marker_contract"):
        module.workflow.materialize(
            Context(
                goal="Inspect",
                inputs={"markers": {}, "output": str(tmp_path / "out.json")},
                facts={},
            )
        )


def test_cli_dispatches_public_mcp_command_without_copying_its_parser(monkeypatch):
    calls = []
    monkeypatch.setattr("apixly_jev_harness.mcp.main", lambda argv: calls.append(argv) or 7)
    assert cli.main(["mcp", "task.py", "--goal", "Investigate"]) == 7
    assert calls == [["task.py", "--goal", "Investigate"]]


def test_machine_spec_exposes_toolkits_factories_and_single_path_mcp(capsys):
    assert task_cli.main(["spec"]) == 0
    spec = json.loads(capsys.readouterr().out)
    assert spec["commands"]["init-task"]["toolkit_choices"] == list(TOOLKITS)
    assert spec["commands"]["init-task"]["default"] == "counter"
    assert spec["script_contract"]["factory"]["inputs"] == "validated_runtime_inputs"
    assert spec["script_contract"]["parameters"]["Parameter"] == [
        "description",
        "choices",
        "depends_on",
        "selection",
    ]
    assert spec["toolkits"]["built_in"] == list(TOOLKITS)
    assert spec["toolkits"]["observation"] == "stable_compact_source_references"
    assert spec["evidence"]["raw_text_read_limit"] == 1200
    assert spec["mcp"]["tools"] == ["observe", "arguments", "operate", "delegate"]
    assert spec["mcp"]["route_selection"] == "before_first_operation"
    assert spec["mcp"]["switch_after_operations"] is False
    assert spec["mcp"]["automatic_delegation_claim"] is False


@pytest.mark.parametrize("complete", [True, False])
def test_cli_run_closes_owned_thin_toolkits_after_terminal_result(
    tmp_path, capsys, monkeypatch, complete
):
    target = tmp_path / "thin.py"
    marker = tmp_path / "closed.txt"
    target.write_text("""from pathlib import Path
from apixly_jev_harness import Task, TaskScript

def build(inputs):
    class Pack:
        def close(self):
            print("PRIVATE_CLEANUP_TEXT")
            Path(inputs["close_marker"]).write_text("closed")
    task = Task(observe=lambda c: {}, verify=lambda c, s: False)
    task.toolkits = [Pack()]
    return task
workflow = TaskScript(build)
""")

    def run(self, workflow, **kwargs):
        workflow.materialize(Context(goal=kwargs["goal"], inputs=kwargs["inputs"], facts={}))
        return {
            "status": "done" if complete else "blocked",
            "complete": complete,
            "telemetry": {"usage_complete": False},
        }

    monkeypatch.setattr(task_cli.AgentLoop, "run", run)
    code = task_cli.main(
        [
            "run",
            str(target),
            "--goal",
            "Inspect",
            "--inputs",
            json.dumps({"close_marker": str(marker)}),
        ]
    )
    output = capsys.readouterr().out
    assert code == (0 if complete else 2)
    assert marker.read_text() == "closed"
    assert "PRIVATE_CLEANUP_TEXT" not in output
    packet = json.loads(output)
    assert packet["telemetry"]["usage_complete"] is False


def test_cleanup_failure_keeps_verified_terminal_and_unknown_usage(tmp_path, capsys, monkeypatch):
    target = tmp_path / "thin.py"
    target.write_text("""from apixly_jev_harness import Task, TaskScript

def build(inputs):
    class Pack:
        def close(self):
            raise RuntimeError("PRIVATE_CLEANUP_ERROR")
    task = Task(observe=lambda c: {}, verify=lambda c, s: False)
    task.toolkits = [Pack()]
    return task
workflow = TaskScript(build)
""")

    def run(self, workflow, **kwargs):
        workflow.materialize(Context(goal=kwargs["goal"], inputs=kwargs["inputs"], facts={}))
        return {"status": "done", "complete": True, "telemetry": {"usage_complete": False}}

    monkeypatch.setattr(task_cli.AgentLoop, "run", run)
    assert task_cli.main(["run", str(target), "--goal", "Inspect"]) == 0
    output = capsys.readouterr().out
    assert "PRIVATE_CLEANUP_ERROR" not in output
    packet = json.loads(output)
    assert packet["status"] == "done" and packet["telemetry"]["usage_complete"] is False
    assert packet["cleanup_errors"] == [{"toolkit_type": "Pack", "error_type": "RuntimeError"}]
