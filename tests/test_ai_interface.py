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


def test_machine_spec_exposes_safe_optional_diagnostic(capsys):
    assert main(["spec"]) == 0
    diagnostic = json.loads(capsys.readouterr().out)["diagnostic"]
    assert diagnostic["optional"] is True
    assert diagnostic["scope"] == "selection_calls"
    assert diagnostic["stages"] == ["tool_selection", "parameter_selection"]
    assert diagnostic["automatic_retry"] is False
    assert "credentials_missing" in diagnostic["reason_codes"]
    assert "model_review" in diagnostic["reason_codes"]
    assert diagnostic["http_code_pattern"] == "http_[1-5][0-9]{2}_body_suppressed"
    assert diagnostic["raw_exception_text"] is False
    assert diagnostic["bound_values"] is False


def test_machine_spec_distinguishes_next_tool_from_record_choice(capsys):
    assert main(["spec"]) == 0
    spec = json.loads(capsys.readouterr().out)
    tool = spec["tool_selection"]
    assert tool["scope"] == "next_step"
    assert tool["decision_stage_field"] == "decision_stage"
    assert tool["requirements_source"] == "caller_task_contract"
    assert tool["candidate_order_is_priority"] is False
    assert tool["direct_choice_without_loop_marker"] == "unchanged"


def test_machine_spec_describes_static_checker_without_execution(capsys):
    assert main(["spec"]) == 0
    check = json.loads(capsys.readouterr().out)["commands"]["check-task"]
    assert check["checks"] == ["utf8_decode", "ast_parse", "python_compile", "top_level_assignment"]
    assert check["python_scope"] == "current_interpreter"
    assert check["source_execution"] is False
    assert check["runtime_validation"] is False
    assert check["source_warning_code"] == "python_source_warning"


def test_machine_spec_describes_configuration_preflight(capsys):
    assert main(["spec"]) == 0
    preflight = json.loads(capsys.readouterr().out)["commands"]["run"]["configuration_preflight"]
    assert preflight["before_task_module_loading"] is True
    assert preflight["shared_with_engine"] is True
    assert preflight["defaults_for"] == "None only"
    assert preflight["failure_code"] == "invalid_run_configuration"
    assert preflight["sandbox"] is False


def test_machine_spec_exposes_synchronous_callback_contract(capsys):
    assert main(["spec"]) == 0
    callbacks = json.loads(capsys.readouterr().out)["callbacks"]
    assert callbacks["execution"] == "synchronous"
    assert callbacks["provider_positional_arguments"] == [2, 3]
    assert callbacks["provider_preferred_arity"] == 3
    assert callbacks["admission_invokes_body"] is False
    assert callbacks["generator_exception"] == "Workflow.candidates"
    assert "synchronous_callback_required" in callbacks["error_codes"]
    assert callbacks["fallback_error_code"] == "callback_contract_error"


def test_machine_spec_exposes_cli_task_output_scope(capsys):
    assert main(["spec"]) == 0
    output = json.loads(capsys.readouterr().out)["commands"]["run"]["task_output"]
    assert output["policy"] == "discard"
    assert output["scope"] == "python_streams"
    assert output["retains_content"] is False
    assert output["sdk_behavior"] == "unchanged"
    assert output["fd_isolation"] is False
    assert output["base_exception_terminal_guarantee"] is False


def test_machine_spec_exposes_argument_error_boundary(capsys):
    assert main(["spec"]) == 0
    parsing = json.loads(capsys.readouterr().out)["argument_parsing"]
    assert parsing["failure_phase"] == "arguments"
    assert parsing["failure_code"] == "invalid_command_arguments"
    assert parsing["failure_exit_code"] == 2
    assert parsing["scope"] == "all command parsers when argparse reports an error"
    assert parsing["raw_argument_values"] is False
    assert parsing["script_loaded_on_failure"] is False
    assert parsing["model_calls_on_failure"] == 0
    assert parsing["help"] == "text and SystemExit(0); original precedence"


def test_machine_spec_exposes_loop_context_budget_unit_and_scope(capsys):
    assert main(["spec"]) == 0
    spec = json.loads(capsys.readouterr().out)
    budget = spec["context_admission"]
    assert spec["limits"]["decision_context_characters"] == budget["limit"] == 15000
    assert budget["unit"] == "json_characters"
    assert budget["maximum_is_inclusive"] is True
    assert budget["metadata_field"] == "context_budget"
    assert budget["full_prompt_or_token_budget"] is False
    assert budget["direct_decide_admission"] == "unchanged"


def test_machine_spec_exposes_current_selection_planner_deferral(capsys):
    assert main(["spec"]) == 0
    spec = json.loads(capsys.readouterr().out)
    planning = spec["request_planning"]
    assert planning["scope"] == "current_selection"
    assert planning["metadata_field"] == "telemetry.planning or telemetry.calls[].planning"
    assert planning["empty_plan_inference_dispatched"] is False
    assert planning["whole_run_zero_calls_or_effects"] is False
    assert planning["arbitrary_validation_error_classification"] is False
    assert "request_needs_narrowing" in spec["diagnostic"]["reason_codes"]


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
