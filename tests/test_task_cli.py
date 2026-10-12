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
    target.write_text("caller-owned source", encoding="utf-8", newline="\n")
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
        (root / "facts.txt").write_text(synthetic_page()["text"], encoding="utf-8", newline="\n")
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
    assert spec["commands"]["init-task"]["toolkit_choices"] == [*TOOLKITS, "surface", "records"]
    assert spec["commands"]["init-task"]["default"] == "counter"
    assert spec["script_contract"]["factory"]["inputs"] == "validated_runtime_inputs"
    assert spec["script_contract"]["parameters"]["Parameter"] == [
        "description",
        "choices",
        "depends_on",
        "selection",
    ]
    assert spec["toolkits"]["built_in"] == [*TOOLKITS, "surface", "records"]
    assert spec["toolkits"]["observation"] == "stable_compact_source_references"
    assert spec["evidence"]["raw_text_read_limit"] == 1200
    assert spec["mcp"]["tools"] == ["observe", "arguments", "operate", "run_task", "read_report"]
    assert "execution-name" in spec["commands"]["mcp"]["optional"]
    assert spec["mcp"]["report_read"]["records_per_page"] == 4
    assert spec["mcp"]["route_selection"] == "before_first_operation"
    assert spec["mcp"]["switch_after_operations"] is False
    assert spec["mcp"]["automatic_delegation_claim"] is False


def test_quickstart_is_compact_offline_interface_without_route_preference(capsys, monkeypatch):
    monkeypatch.setattr(task_cli.AgentLoop, "run", lambda *a, **k: pytest.fail("inference"))
    assert task_cli.main(["quickstart"]) == 0
    output = capsys.readouterr().out
    packet = json.loads(output)
    assert len(output.encode()) < 4000
    assert packet["model_calls"] == 0
    assert packet["script"]["factory"] == "build(inputs) -> Task"
    assert packet["tools"]["parameter_values"] == "caller_supplied_candidates"
    assert packet["cli"]["run"].startswith("jev-harness run ")
    assert packet["outcome"]["completion"] == "caller_independent_verifier"
    assert "prefer" not in output.lower() and "must use" not in output.lower()


@pytest.mark.parametrize("complete", [True, False])
def test_cli_run_closes_owned_thin_toolkits_after_terminal_result(
    tmp_path, capsys, monkeypatch, complete
):
    target = tmp_path / "thin.py"
    marker = tmp_path / "closed.txt"
    target.write_text(
        """from pathlib import Path
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
""",
        newline="\n",
    )

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
    target.write_text(
        """from apixly_jev_harness import Task, TaskScript

def build(inputs):
    class Pack:
        def close(self):
            raise RuntimeError("PRIVATE_CLEANUP_ERROR")
    task = Task(observe=lambda c: {}, verify=lambda c, s: False)
    task.toolkits = [Pack()]
    return task
workflow = TaskScript(build)
""",
        newline="\n",
    )

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


def test_quickstart_documents_the_authorize_action_shape_it_actually_receives(capsys, tmp_path):
    from apixly_jev_harness import Engine, Option, Parameter, Task

    assert task_cli.main(["quickstart"]) == 0
    packet = json.loads(capsys.readouterr().out)
    authorization = packet["tools"]["authorization"]
    assert "irreversible=True" in authorization and "authorize(ctx, action)" in authorization
    assert "{'tool': name, 'arguments':" in authorization
    assert "SurfaceTask(" in packet["toolkits"]["surface"]
    seen, effects = [], []
    task = Task(
        observe=lambda ctx: {"done": bool(effects)},
        verify=lambda ctx, state: state["done"],
        authorize=lambda ctx, action: seen.append(action.params) or False,
    )

    @task.tool(
        "Save the synthetic draft",
        name="save",
        irreversible=True,
        parameters={"target": Parameter("Draft", lambda c, s: [Option("d", "draft", {"id": 7})])},
    )
    def save(target):
        effects.append(target)

    class Scripted(Engine):
        def decide(self, records, goal, **kwargs):
            return {
                "ok": True,
                "complete": True,
                "selected_ids": ["save"],
                "review_ids": [],
                "telemetry": {"requests": 0, "usage_complete": False, "usage": None},
            }

    result = Scripted().run(task, goal="Save the draft", archive=tmp_path / "run.jsonl")
    assert result["status"] == "needs_confirmation" and effects == []
    assert seen == [{"tool": "save", "arguments": {"target": {"id": 7}}}]


class ControlSurface:
    def __init__(self, text="Draft form"):
        self.text = text
        self.actions = [
            {"id": "save", "kind": "click", "label": "Save draft", "role": "button"},
            {"id": "send", "kind": "click", "label": "Send now", "role": "button"},
            {"id": "title", "kind": "fill", "label": "Title", "role": "textbox", "value": ""},
        ]

    def observe(self):
        return {
            "fingerprint": self.text,
            "url": "https://form.test/draft",
            "text": self.text,
            "actions": self.actions,
        }

    def fresh(self, state, target):
        return True

    def act(self, target, state, text=None):
        return {"executed": target["id"]}

    def settle(self, target):
        pass


def test_surface_scaffold_binds_named_values_scoped_clicks_and_a_verifier(
    tmp_path, capsys, monkeypatch
):
    target = scaffold(tmp_path, capsys, "surface")
    assert task_cli.main(["check-task", str(target)]) == 0
    assert json.loads(capsys.readouterr().out)["code"] == "syntax_and_export_ok"
    module = load(target)
    assert isinstance(module.workflow, TaskScript) and module.workflow._task is None
    surface = ControlSurface()
    monkeypatch.setattr(module, "open_surface", lambda inputs: surface)
    inputs = {
        "url": "https://form.test/draft",
        "values": {"title": "Weekly digest"},
        "done_text": "Draft saved",
    }
    ctx = Context(goal="Save the draft", inputs=inputs, facts={})
    task = module.workflow.materialize(ctx)
    state = task.observe(ctx)
    assert task.verify(ctx, state) is False
    offered = {a.params["tool"]: a for a in task.candidates(ctx, state)}
    assert set(offered) == {"click", "fill"}
    choices = iter(["save", "send"])

    def choose(records, goal, extra=None):
        return {"ok": True, "complete": True, "selected_ids": [next(choices)]}

    allowed = task.bind(ctx, state, offered["click"], choose)
    assert task.authorize(ctx, allowed) is True
    denied = task.bind(ctx, state, task.candidates(ctx, state)[0], choose)
    assert denied.params["arguments"]["target"]["label"] == "Send now"
    assert task.authorize(ctx, denied) is False
    surface.text = "Draft saved"
    assert task.verify(ctx, task.observe(ctx)) is True


def test_surface_scaffold_requires_a_verifier_contract_before_opening_a_surface(
    tmp_path, capsys, monkeypatch
):
    module = load(scaffold(tmp_path, capsys, "surface"))

    def forbidden(inputs):
        raise AssertionError("verify contract must be checked before surface I/O")

    monkeypatch.setattr(module, "open_surface", forbidden)
    with pytest.raises(ValueError, match="verify_contract_required"):
        module.workflow.materialize(
            Context(goal="Save", inputs={"url": "https://form.test/"}, facts={})
        )


def test_records_scaffold_judges_all_records_once_and_saves_matching_ids(
    tmp_path, capsys, monkeypatch
):
    target = scaffold(tmp_path, capsys, "records")
    assert task_cli.main(["check-task", str(target)]) == 0
    assert json.loads(capsys.readouterr().out)["code"] == "syntax_and_export_ok"
    module = load(target)
    assert module.workflow._task is None
    source = tmp_path / "records.jsonl"
    lines = [json.dumps({"id": f"r{i}", "text": f"event {i}"}) for i in range(5)]
    source.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    calls = []

    def decide(self, records, *, goal, analysis_spec):
        calls.append((len(records), goal, analysis_spec["filter"]))
        return {"selected_ids": ["r1", "r3"], "review_ids": ["r4"], "complete": True}

    monkeypatch.setattr("apixly_jev_harness.Engine.decide", decide)
    output = tmp_path / "report.json"
    inputs = {"records": str(source), "output": str(output), "question": "Is it odd?"}
    ctx = Context(goal="Triage", inputs=inputs, facts={})
    task = module.workflow.materialize(ctx)
    state = task.observe(ctx)
    assert task.verify(ctx, state) is False
    action = task.candidates(ctx, state)[0]
    bound = task.bind(ctx, state, action, lambda *args: None)
    assert task.execute(ctx, bound) == {"ids": 2, "review_ids": 1, "complete": True}
    assert task.verify(ctx, task.observe(ctx)) is True
    assert json.loads(output.read_text())["ids"] == ["r1", "r3"]
    assert calls == [(5, "Is it odd?", {"question": "match", "in": ["MATCH"]})]


def test_records_scaffold_requires_question_and_unique_records(tmp_path, capsys):
    module = load(scaffold(tmp_path, capsys, "records"))
    source = tmp_path / "records.jsonl"
    rows = [{"id": "a", "text": "x"}, {"id": "a", "text": "y"}]
    source.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    base = {"records": str(source), "output": str(tmp_path / "out.json")}
    with pytest.raises(ValueError, match="question_required"):
        module.workflow.materialize(Context(goal="t", inputs=base, facts={}))
    with pytest.raises(ValueError, match="unique_records_required"):
        module.workflow.materialize(Context(goal="t", inputs={**base, "question": "q"}, facts={}))
