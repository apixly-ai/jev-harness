import copy
from enum import Enum, IntEnum

import pytest

from apixly_jev_harness import Action, AgentLoop, Task


def registered(value, strategy="staged"):
    effects = []
    task = Task(observe=lambda ctx: {}, verify=lambda ctx, seen: False, strategy=strategy)

    @task.tool("Store the offered value", parameters={"value": [value]})
    def store(value):
        effects.append(value)
        return value

    offered = task.candidates(None, {})[0]
    bound = task.bind(None, {}, offered, lambda *args: pytest.fail("singleton inference"))
    return task, offered, bound, effects


MISMATCHES = [
    (True, 1),
    (False, 0),
    (1, True),
    (0, False),
    ([True], [1]),
    ({"enabled": False}, {"enabled": 0}),
    (({"enabled": True},), ({"enabled": 1},)),
    ({True: "enabled"}, {1: "enabled"}),
    ({0: "disabled"}, {False: "disabled"}),
]


@pytest.mark.parametrize("original,replacement", MISMATCHES)
@pytest.mark.parametrize("strategy", ["staged", "joint"])
def test_execute_rejects_bool_number_changes_to_bound_value(original, replacement, strategy):
    task, _, bound, effects = registered(original, strategy)
    changed = copy.deepcopy(bound)
    changed.params["arguments"]["value"] = replacement
    with pytest.raises(ValueError, match="action_not_bound"):
        task.execute(None, changed)
    assert effects == []


@pytest.mark.parametrize("original,replacement", MISMATCHES)
def test_joint_bind_rejects_changes_to_offered_arguments(original, replacement):
    task, offered, _, effects = registered(original, "joint")
    changed = copy.deepcopy(offered)
    changed.params["arguments"]["value"] = replacement
    with pytest.raises(ValueError, match="action_not_offered"):
        task.bind(None, {}, changed, lambda *args: pytest.fail("joint inference"))
    assert effects == []


@pytest.mark.parametrize("phase", ["bind", "execute"])
def test_invalid_boolean_metadata_cannot_match_snapshot(phase):
    task, _, bound, effects = registered(True, "joint")
    changed = copy.deepcopy(bound)
    object.__setattr__(changed, "irreversible", 0)
    with pytest.raises(
        ValueError, match="action_not_offered" if phase == "bind" else "action_not_bound"
    ):
        if phase == "bind":
            task.bind(None, {}, changed, None)
        else:
            task.execute(None, changed)
    assert effects == []


@pytest.mark.parametrize("phase", ["bind", "execute"])
def test_custom_description_equality_does_not_admit_changed_action(phase):
    equality_calls = []

    class Description(str):
        def __eq__(self, other):
            equality_calls.append(1)
            return True

    task, _, bound, effects = registered(True, "joint")
    changed = Action(bound.id, Description("different description"), bound.params)
    with pytest.raises(
        ValueError, match="action_not_offered" if phase == "bind" else "action_not_bound"
    ):
        if phase == "bind":
            task.bind(None, {}, changed, None)
        else:
            task.execute(None, changed)
    assert effects == [] and equality_calls == []


@pytest.mark.parametrize("original,replacement", [(1, 1.0), (1.0, 1), ({1: True}, {1.0: True})])
@pytest.mark.parametrize("strategy", ["staged", "joint"])
def test_finite_numeric_equivalence_remains_supported(original, replacement, strategy):
    task, _, bound, effects = registered(original, strategy)
    changed = copy.deepcopy(bound)
    changed.params["arguments"]["value"] = replacement
    assert task.execute(None, changed) == replacement
    assert effects == [replacement]


def test_global_action_equality_is_not_changed():
    assert Action("a", "Description", {"enabled": True}) == Action(
        "a", "Description", {"enabled": 1}
    )


def test_action_subclass_does_not_gain_fieldwise_admission():
    class OtherAction(Action):
        pass

    task, _, bound, effects = registered(True)
    other = OtherAction(bound.id, bound.description, bound.params)
    with pytest.raises(ValueError, match="action_not_bound"):
        task.execute(None, other)
    assert effects == []


@pytest.mark.parametrize("phase", ["bind", "execute"])
def test_spoofed_action_class_does_not_supply_guard_equality(phase):
    equality_calls = []

    class OtherAction(Action):
        def __eq__(self, other):
            equality_calls.append(1)
            return True

    task, _, bound, effects = registered(True, "joint")
    other = OtherAction(bound.id, bound.description, bound.params)
    with pytest.raises(
        ValueError, match="action_not_offered" if phase == "bind" else "action_not_bound"
    ):
        if phase == "bind":
            task.bind(None, {}, other, None)
        else:
            task.execute(None, other)
    assert effects == [] and equality_calls == []


def test_action_id_subclass_is_rejected_before_dictionary_lookup():
    equality_calls = []

    class Identifier(str):
        __hash__ = str.__hash__

        def __eq__(self, other):
            equality_calls.append(1)
            return True

    task, _, bound, effects = registered(True)
    changed = Action(Identifier(bound.id), bound.description, bound.params)
    with pytest.raises(ValueError, match="action_not_bound"):
        task.execute(None, changed)
    assert effects == [] and equality_calls == []


class NumericMode(IntEnum):
    ONE = 1


class TextMode(str, Enum):
    CURRENT = "current"


class Record(dict):
    pass


@pytest.mark.parametrize("value", [NumericMode.ONE, TextMode.CURRENT, Record(enabled=True)])
def test_unchanged_custom_values_require_caller_normalization(value):
    task, _, bound, effects = registered(value)
    with pytest.raises(ValueError, match="action_not_bound"):
        task.execute(None, bound)
    assert effects == []


@pytest.mark.parametrize("strategy", ["staged", "joint"])
def test_engine_keeps_existing_guard_error_window_and_unknown_usage(
    strategy, monkeypatch, tmp_path
):
    task = Task(observe=lambda ctx: {}, verify=lambda ctx, seen: False, strategy=strategy)
    effects = []

    @task.tool("Use a supplied mode", parameters={"mode": [NumericMode.ONE]})
    def use(mode):
        effects.append(mode)

    def choose(parts, *args):
        return {
            part["id"]: {"status": "OK", "decision": "MATCH" if i == 0 else "EXCLUDE"}
            for i, part in enumerate(parts)
        }, {"ok": True, "requests": 1, "usage_complete": False, "usage": None}

    monkeypatch.setattr("apixly_jev_harness.engine.analysis.evaluate", choose)
    monkeypatch.setattr(
        "apixly_jev_harness.backend.native_run",
        lambda *args, **kwargs: pytest.fail("native inference"),
    )
    result = AgentLoop().run(task, goal="Use supplied mode", archive=tmp_path / "run.jsonl")
    assert result["status"] == ("failed" if strategy == "joint" else "execution_uncertain")
    assert result["steps"] == 0 and effects == []
    assert result["telemetry"]["requests"] == 1
    assert result["telemetry"]["usage_complete"] is False and result["telemetry"]["usage"] is None
    assert ("action_id" in result) is (strategy == "staged")


def test_machine_contract_describes_guard_semantics():
    from apixly_jev_harness.task_cli import SPEC

    contract = SPEC["task_action_identity"]
    assert contract["boolean_number_equality"] is False
    assert contract["finite_int_float_equality"] is True
    assert contract["global_action_equality_changed"] is False
    assert contract["engine_guard_rejection_always_failed"] is False
