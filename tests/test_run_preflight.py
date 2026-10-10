import json

import pytest

from apixly_jev_harness import AgentLoop, Task
from apixly_jev_harness.task_cli import main

BAD_OPTIONS = [
    ["--goal", " "],
    ["--messages", "{"],
    ["--messages", "{}"],
    ["--messages", '[{"role":"system","content":"policy"}]'],
    ["--messages", '[{"role":"user","content":1}]'],
    ["--max-steps", "0"],
    ["--max-steps", "-1"],
    ["--timeout", "0"],
    ["--timeout", "nan"],
    ["--timeout", "inf"],
    ["--required-context", ""],
    ["--required-context", "tenant..id"],
    ["--inputs", '{"amount":NaN}'],
    ["--context", '{"amount":Infinity}'],
    ["--messages", '[{"role":"user","content":"text","extra":NaN}]'],
    ["--inputs", "null"],
    ["--context", "null"],
    ["--messages", "null"],
    ["--inputs", '{"text":"\\ud800"}'],
    ["--context", '{"text":"\\ud800"}'],
    ["--messages", '[{"role":"user","content":"\\ud800"}]'],
]


@pytest.mark.parametrize("options", BAD_OPTIONS)
def test_invalid_run_options_never_load_the_script(tmp_path, capsys, monkeypatch, options):
    marker = tmp_path / "import-effect.txt"
    script = tmp_path / "task.py"
    script.write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('import happened')\n"
        "from apixly_jev_harness import Task\n"
        "workflow = Task(observe=lambda ctx: {'done': True}, verify=lambda ctx, seen: seen['done'])\n"
    )
    model_calls = []
    loader_calls = []
    from apixly_jev_harness import task_cli

    original = task_cli.importlib.util.spec_from_file_location

    def loader(*args, **kwargs):
        loader_calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(task_cli.importlib.util, "spec_from_file_location", loader)
    monkeypatch.setattr(
        "apixly_jev_harness.backend.provider_evaluate", lambda *a, **k: model_calls.append(1)
    )
    assert main(["run", str(script), "--goal", "Observe completed fixture", *options]) == 2
    packet = json.loads(capsys.readouterr().out)
    assert packet["status"] == "failed"
    assert packet["phase"] == "configuration"
    assert packet["script_loaded"] is False
    assert packet["model_calls"] == 0
    assert not marker.exists()
    assert model_calls == []
    assert loader_calls == []


@pytest.mark.parametrize(
    "options",
    [{"inputs": []}, {"context": False}, {"messages": {}}, {"messages": False}],
)
def test_falsey_wrong_sdk_types_are_not_replaced_with_defaults(options, tmp_path):
    observed = []
    task = Task(observe=lambda ctx: observed.append(1) or {}, verify=lambda ctx, state: True)
    with pytest.raises(ValueError):
        AgentLoop().run(task, goal="Observe", archive=tmp_path / "run.jsonl", **options)
    assert observed == []
    assert not (tmp_path / "run.jsonl").exists()


def test_valid_configuration_still_loads_and_runs_trusted_module(tmp_path, capsys):
    marker = tmp_path / "import-effect.txt"
    script = tmp_path / "task.py"
    script.write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('trusted import')\n"
        "from apixly_jev_harness import Task\n"
        "workflow=Task(observe=lambda ctx: {'done': True}, verify=lambda ctx, seen: seen['done'])\n"
    )
    assert main(["run", str(script), "--goal", "Observe completed fixture"]) == 0
    packet = json.loads(capsys.readouterr().out)
    assert packet["status"] == "done"
    assert packet["telemetry"]["requests"] == 0
    assert marker.exists()


def test_missing_required_fact_remains_runtime_needs_context(tmp_path, capsys):
    script = tmp_path / "task.py"
    script.write_text(
        "from apixly_jev_harness import Task\nworkflow=Task(observe=lambda ctx: {}, verify=lambda ctx, state: True)\n"
    )
    assert main(["run", str(script), "--goal", "Observe", "--required-context", "tenant.id"]) == 2
    packet = json.loads(capsys.readouterr().out)
    assert packet["status"] == "needs_context"
    assert packet["missing_context"] == ["tenant.id"]
    assert packet["telemetry"]["requests"] == 0


def test_one_pass_required_paths_are_not_consumed_twice(tmp_path):
    task = Task(observe=lambda ctx: {}, verify=lambda ctx, state: True)
    result = AgentLoop().run(
        task, goal="Observe", required_context=iter(["tenant.id"]), archive=tmp_path / "run.jsonl"
    )
    assert result["status"] == "needs_context"
    assert result["missing_context"] == ["tenant.id"]


def test_invalid_config_does_not_echo_input_or_exception_text(tmp_path, capsys):
    script = tmp_path / "task.py"
    script.write_text("raise RuntimeError('must not load')\nworkflow=None\n")
    assert (
        main(["run", str(script), "--goal", "Observe", "--messages", "PRIVATE_JSON_FRAGMENT"]) == 2
    )
    output = capsys.readouterr().out
    assert "PRIVATE_JSON_FRAGMENT" not in output
    assert "must not load" not in output
    assert json.loads(output)["script_loaded"] is False


def test_sdk_none_defaults_remain_valid(tmp_path):
    task = Task(
        observe=lambda ctx: {
            "defaults": ctx.inputs == {} and ctx.facts == {} and ctx.messages == []
        },
        verify=lambda ctx, state: state["defaults"],
    )
    result = AgentLoop().run(
        task,
        goal="Observe defaults",
        inputs=None,
        context=None,
        messages=None,
        archive=tmp_path / "run.jsonl",
    )
    assert result["status"] == "done"
    assert result["telemetry"]["requests"] == 0


def test_sdk_unencodable_goal_is_rejected_before_journal_or_callback(tmp_path):
    observed = []
    task = Task(observe=lambda ctx: observed.append(1) or {}, verify=lambda ctx, state: True)
    with pytest.raises(UnicodeEncodeError):
        AgentLoop().run(task, goal="\ud800", archive=tmp_path / "run.jsonl")
    assert observed == []
    assert not (tmp_path / "run.jsonl").exists()
