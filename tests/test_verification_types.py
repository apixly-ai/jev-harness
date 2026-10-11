import json

import pytest

from apixly_jev_harness import AgentLoop, Task, verify_state
from apixly_jev_harness.task_cli import SPEC, main


@pytest.mark.parametrize(
    "expected,observed",
    [
        (True, 1),
        (False, 0),
        (1, True),
        (0, False),
        ({"items": [False]}, {"items": [0]}),
        ([{"enabled": True}], [{"enabled": 1}]),
        ((False,), (0,)),
        ({True: "same"}, {1: "same"}),
        ({False: ["same"]}, {0: ["same"]}),
    ],
)
def test_boolean_numeric_mismatch_cannot_claim_initial_completion(
    monkeypatch, tmp_path, expected, observed
):
    def forbidden(*args, **kwargs):
        raise AssertionError("No semantic call needed for exact verification")

    monkeypatch.setattr("apixly_jev_harness.backend.native_run", forbidden)
    task = Task(
        observe=lambda ctx: {"controls": [{"label": "Value", "value": observed}]},
        verify=verify_state(controls=[{"label": "Value", "value": expected}]),
    )
    result = AgentLoop().run(task, goal="Observe exact condition", archive=tmp_path / "run.jsonl")
    assert result["status"] == "blocked" and result["reason"] == "no_candidates"
    assert result["complete"] is False and result["steps"] == 0
    assert result["telemetry"]["requests"] == 0
    assert result["telemetry"]["owned_transport"]["request_attempts"] == 0


@pytest.mark.parametrize("observed", [["Complete"], {"Complete": "unrelated"}, None, 123])
def test_text_membership_requires_observed_string(tmp_path, observed):
    task = Task(observe=lambda ctx: {"text": observed}, verify=verify_state(text="Complete"))
    result = AgentLoop().run(task, goal="Observe completion text", archive=tmp_path / "run.jsonl")
    assert result["status"] == "blocked" and result["complete"] is False
    assert result["steps"] == result["telemetry"]["requests"] == 0


def test_unsupported_equality_object_cannot_prove_completion_or_invoke_equality(tmp_path):
    called = []

    class Unknown:
        def __eq__(self, other):
            called.append(1)
            return True

    task = Task(
        observe=lambda ctx: {"controls": [{"label": "Value", "value": 0}]},
        verify=verify_state(controls=[{"label": "Value", "value": Unknown()}]),
    )
    result = AgentLoop().run(task, goal="Observe exact condition", archive=tmp_path / "run.jsonl")
    assert result["status"] == "blocked" and called == []


@pytest.mark.parametrize(
    "expected,observed,matched",
    [
        (True, True, True),
        (False, False, True),
        (True, False, False),
        (1, 1.0, True),
        (1.0, 1, True),
        (1, 2, False),
        ({1: "same"}, {1.0: "same"}, True),
        ({"items": [None, True, 1.0]}, {"items": [None, True, 1]}, True),
        ((False, 1.0), (False, 1), True),
        ((1,), [1], False),
        ([1], (1,), False),
        ({"a": 1}, {"a": 1, "b": 2}, False),
    ],
)
def test_supported_value_compatibility_and_complete_structure(expected, observed, matched):
    verifier = verify_state(controls=[{"label": "Value", "value": expected}])
    assert verifier(None, {"controls": [{"label": "Value", "value": observed}]}) is matched


def test_valid_text_substring_missing_null_and_duplicate_guards_remain():
    assert verify_state(text="Complete")(None, {"text": "Status: Complete now"}) is True
    verifier = verify_state(controls=[{"label": "Value", "value": None}])
    assert verifier(None, {"controls": [{"label": "Value"}]}) is False
    assert verifier(None, {"controls": [{"label": "Value", "value": None}]}) is True
    assert verifier(None, {"controls": [{"label": "Value", "value": None}] * 2}) is False


def test_typed_false_condition_can_continue_and_verify_real_observed_progress(
    monkeypatch, tmp_path
):
    state = {"controls": [{"label": "Approved", "checked": 1}]}
    effects = []
    task = Task(
        observe=lambda ctx: dict(state),
        verify=verify_state(controls=[{"label": "Approved", "checked": True}]),
    )

    @task.tool("Collect correct typed observation")
    def collect():
        effects.append(1)
        state["controls"] = [{"label": "Approved", "checked": True}]

    def choose(parts, *args):
        return {
            p["id"]: {"status": "OK", "decision": "MATCH" if i == 0 else "EXCLUDE"}
            for i, p in enumerate(parts)
        }, {"ok": True, "requests": 1, "usage_complete": False, "usage": None}

    monkeypatch.setattr("apixly_jev_harness.engine.analysis.evaluate", choose)
    result = AgentLoop().run(task, goal="Verify typed approval", archive=tmp_path / "run.jsonl")
    assert result["status"] == "done" and result["steps"] == 1 and effects == [1]
    assert result["telemetry"]["usage"] is None
    events = [json.loads(line) for line in (tmp_path / "run.jsonl").read_text().splitlines()]
    assert [e["passed"] for e in events if e["event"] == "verified"] == [False, True]


def test_machine_contract_defines_value_families_and_text_type():
    verification = SPEC["verification"]
    assert verification["observed_text_requires"] == "str; otherwise does not match"
    assert verification["boolean_number_equality"] is False
    assert verification["numeric_int_float_equality"] is True
    assert verification["unsupported_helper_values"] == "do not match; custom verifier required"


def test_expected_field_names_cannot_delegate_lookup_to_custom_equality():
    called = []

    class Field:
        def __hash__(self):
            return hash("checked")

        def __eq__(self, other):
            called.append(1)
            return other == "checked"

    condition = {"label": "Approved", Field(): True}
    with pytest.raises(ValueError, match="control_check_requires_label_and_expected_fields"):
        verify_state(controls=[condition])
    assert called == []


def test_observed_field_names_cannot_impersonate_other_fields():
    called = []

    class Field(str):
        def __hash__(self):
            return hash("checked")

        def __eq__(self, other):
            called.append(1)
            return other == "checked"

    control = {"label": "Approved", Field("unrelated"): True}
    verifier = verify_state(controls=[{"label": "Approved", "checked": True}])
    assert verifier(None, {"controls": [control]}) is False and called == []


@pytest.mark.parametrize("invalid", [None, "unknown", [], {"label": "Approved", "checked": True}])
def test_unrecognized_control_records_cannot_be_discarded_to_prove_uniqueness(invalid):
    verifier = verify_state(controls=[{"label": "Approved", "checked": True}])
    controls = [{"label": "Approved", "checked": True}, invalid]
    assert verifier(None, {"controls": controls}) is False


def test_unsupported_metaclass_cannot_impersonate_numeric_value_family():
    called = []

    class Kind(type):
        __hash__ = type.__hash__

        def __eq__(cls, other):
            called.append("metaclass")
            return True

    class Unknown(metaclass=Kind):
        def __float__(self):
            called.append("float")
            return 0.0

        def __eq__(self, other):
            called.append("value")
            return True

    verifier = verify_state(controls=[{"label": "Value", "value": Unknown()}])
    called.clear()
    assert verifier(None, {"controls": [{"label": "Value", "value": 0}]}) is False
    assert called == []


@pytest.mark.parametrize("field", ["text", "controls"])
def test_observation_root_field_alias_cannot_prove_completion(field):
    called = []

    class Field(str):
        def __hash__(self):
            return hash(field)

        def __eq__(self, other):
            called.append(1)
            return other == field

    value = "Complete" if field == "text" else [{"label": "Approved", "checked": True}]
    state = {Field("unrelated"): value}
    verifier = (
        verify_state(text="Complete")
        if field == "text"
        else verify_state(controls=[{"label": "Approved", "checked": True}])
    )
    assert verifier(None, state) is False and called == []


def test_text_subclass_cannot_forge_nonempty_completion_condition():
    called = []

    class EmptyText(str):
        def strip(self):
            called.append(1)
            return "pretended condition"

    with pytest.raises(ValueError, match="verification_text_required"):
        verify_state(text=EmptyText(""))
    assert called == []


def test_cli_numeric_boolean_observation_exits_nonzero_without_false_done(
    monkeypatch, tmp_path, capsys
):
    def forbidden(*args, **kwargs):
        raise AssertionError("No semantic inference is needed")

    monkeypatch.setattr("apixly_jev_harness.backend.native_run", forbidden)
    script = tmp_path / "task.py"
    script.write_text(
        "from apixly_jev_harness import Task,verify_state\n"
        "workflow=Task(observe=lambda ctx:{'controls':[{'label':'Approved','checked':1}]},"
        "verify=verify_state(controls=[{'label':'Approved','checked':True}]))\n"
    )
    assert main(["run", str(script), "--goal", "Observe typed approval"]) == 2
    captured = capsys.readouterr()
    packet = json.loads(captured.out)
    assert packet["status"] == "blocked" and packet["complete"] is False
    assert packet["steps"] == packet["telemetry"]["requests"] == 0
    assert packet["telemetry"]["owned_transport"]["request_attempts"] == 0
    assert captured.err == ""
