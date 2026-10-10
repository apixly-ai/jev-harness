import json

from apixly_jev_harness.task_cli import main


def test_machine_spec_is_self_describing(capsys):
    assert main(["spec"]) == 0
    spec = json.loads(capsys.readouterr().out)
    assert spec["commands"]["run"]["required"] == ["script", "goal"]
    assert spec["parameter_binding"] == "staged_candidate_choice"
    assert spec["exit_codes"]["2"] == "parse_terminal_packet"
    assert spec["script_contract"]["export"] == "workflow"


def test_machine_spec_exposes_progress_and_verification_contract(capsys):
    assert main(["spec"]) == 0
    spec = json.loads(capsys.readouterr().out)
    assert spec["progress"]["unchanged_observation_requires"] == "non_none_admitted_result"
    duplicate = spec["progress"]["duplicate_invocation"]
    assert duplicate["scope"] == "single_run"
    assert duplicate["key"] == ["observation", "action_id", "bound_parameters"]
    assert duplicate["status"] == "blocked"
    assert duplicate["reason"] == "repeated_action_state"
    assert duplicate["effect"] == "not_executed"
    assert spec["verification"]["helper_requires"] == "nonempty_text_or_control_condition"
    assert spec["verification"]["missing_control_fields"] == "do_not_match"


def test_check_task_does_not_execute_module_code(tmp_path, capsys):
    script = tmp_path / "task.py"
    script.write_text('raise RuntimeError("must not execute")\nworkflow = None\n')
    assert main(["check-task", str(script)]) == 0
    assert json.loads(capsys.readouterr().out)["model_calls"] == 0
    script.write_text("workflow = (")
    assert main(["check-task", str(script)]) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "invalid_python"


def test_skill_instructions_are_available_offline(capsys):
    assert main(["skill"]) == 0
    body = capsys.readouterr().out
    assert "name: jev-harness" in body
    assert "jev-harness spec" in body
