import copy
import json

import pytest

from apixly_jev_harness import AgentLoop, Option, Parameter, Task


def scripted_choice(selected, parts, *, unknown=False):
    return {
        part["id"]: {
            "status": "OK",
            "decision": "MATCH" if part["id"] == selected else "EXCLUDE",
        }
        for part in parts
    }, {
        "ok": True,
        "requests": 1,
        "usage_complete": not unknown,
        **({"usage": {"input_tokens": 0, "output_tokens": 0}} if not unknown else {}),
    }


@pytest.mark.parametrize("domain_kind", ["named_dict", "named_list", "raw_dict", "raw_list"])
@pytest.mark.parametrize("unknown", [False, True])
def test_selected_value_is_the_snapshot_described_before_wait(
    domain_kind, unknown, monkeypatch, tmp_path
):
    original = {"record": "synthetic-a"} if domain_kind.endswith("dict") else ["synthetic-a"]
    expected = copy.deepcopy(original)
    named = domain_kind.startswith("named")
    option = Option("current", "Record synthetic-a", original) if named else original
    other = Option("other", "Synthetic record b", {"record": "synthetic-b"}) if named else {}
    effects, providers, calls = [], [], []

    def choices(ctx, seen):
        providers.append(ctx.step)
        return [option, other]

    task = Task(
        observe=lambda ctx: {"processed": copy.deepcopy(effects)},
        verify=lambda ctx, seen: seen["processed"] == [expected],
    )

    @task.tool("Process the described record", parameters={"record": Parameter("Record", choices)})
    def process(record):
        effects.append(record)

    def choose(parts, goal, workers, spec):
        calls.append(spec["context"]["decision_stage"])
        if spec["context"].get("parameter") == "record":
            assert "synthetic-a" in json.dumps(parts)
            if isinstance(original, dict):
                original["record"] = "synthetic-c"
            else:
                original[0] = "synthetic-c"
            return scripted_choice("current" if named else "0", parts, unknown=unknown)
        return scripted_choice("process", parts)

    monkeypatch.setattr("apixly_jev_harness.engine.analysis.evaluate", choose)
    result = AgentLoop().run(
        task, goal="Process described record", max_steps=1, archive=tmp_path / "run.jsonl"
    )
    assert effects == [expected]
    assert result["status"] == "done" and result["steps"] == 1
    assert providers == [0, 0]
    assert calls == ["tool_selection", "parameter_selection"]
    assert result["telemetry"]["requests"] == 2
    assert result["telemetry"]["usage_complete"] is not unknown
    assert (result["telemetry"]["usage"] is None) is unknown


def test_dependent_provider_receives_the_selected_parent_snapshot(monkeypatch, tmp_path):
    parent = {"record": "synthetic-a"}
    parents = [Option("a", "Synthetic record a", parent), Option("b", "Synthetic record b", {})]
    state, effects, seen_parents = {"done": False}, [], []

    def child(ctx, seen, bound):
        seen_parents.append(bound["parent"])
        return [Option("child", "Child of selected record", bound["parent"]["record"] + "-child")]

    task = Task(observe=lambda ctx: dict(state), verify=lambda ctx, seen: seen["done"])

    @task.tool(
        "Inspect selected record and its child",
        parameters={
            "parent": Parameter("Parent record", lambda ctx, seen: parents),
            "child": Parameter("Child record", child, depends_on=("parent",)),
        },
    )
    def inspect(parent, child):
        effects.append((parent, child))
        state["done"] = True

    def choose(parts, goal, workers, spec):
        if spec["context"].get("parameter") == "parent":
            parent["record"] = "synthetic-c"
            return scripted_choice("a", parts)
        return scripted_choice("inspect", parts)

    monkeypatch.setattr("apixly_jev_harness.engine.analysis.evaluate", choose)
    result = AgentLoop().run(task, goal="Inspect parent and child", archive=tmp_path / "run.jsonl")
    assert result["status"] == "done"
    assert seen_parents == [{"record": "synthetic-a"}]
    assert effects == [({"record": "synthetic-a"}, "synthetic-a-child")]


def test_dynamic_domains_still_refresh_between_steps(monkeypatch, tmp_path):
    value = {"record": "synthetic-a"}
    option = Option("current", "Current synthetic record", value)
    state, effects, providers = {"count": 0}, [], []

    def choices(ctx, seen):
        providers.append(ctx.step)
        return [option]

    task = Task(observe=lambda ctx: dict(state), verify=lambda ctx, seen: seen["count"] == 2)

    @task.tool("Process current record", parameters={"record": Parameter("Current", choices)})
    def process(record):
        effects.append(record)
        state["count"] += 1
        value["record"] = "synthetic-b"

    monkeypatch.setattr(
        "apixly_jev_harness.engine.analysis.evaluate",
        lambda parts, *args: scripted_choice("process", parts),
    )
    result = AgentLoop().run(task, goal="Process two records", archive=tmp_path / "run.jsonl")
    assert result["status"] == "done"
    assert effects == [{"record": "synthetic-a"}, {"record": "synthetic-b"}]
    assert providers == [0, 0, 1, 1]
    assert result["telemetry"]["requests"] == 2


def test_binding_refreshes_the_domain_after_tool_selection(monkeypatch, tmp_path):
    value = {"record": "synthetic-a"}
    state, effects, providers = {"done": False}, [], []

    def choices(ctx, seen):
        providers.append(value["record"])
        return [
            Option("current", "Record " + value["record"], value),
            Option("other", "Another record", {}),
        ]

    task = Task(observe=lambda ctx: dict(state), verify=lambda ctx, seen: seen["done"])

    @task.tool("Process the current record", parameters={"record": Parameter("Current", choices)})
    def process(record):
        effects.append(record)
        state["done"] = True

    def choose(parts, goal, workers, spec):
        if spec["context"].get("parameter") == "record":
            assert "synthetic-b" in json.dumps(parts)
            return scripted_choice("current", parts)
        value["record"] = "synthetic-b"
        return scripted_choice("process", parts)

    monkeypatch.setattr("apixly_jev_harness.engine.analysis.evaluate", choose)
    result = AgentLoop().run(task, goal="Process current record", archive=tmp_path / "run.jsonl")
    assert result["status"] == "done"
    assert effects == [{"record": "synthetic-b"}]
    assert providers == ["synthetic-a", "synthetic-b"]


@pytest.mark.parametrize("violation", ["duplicate", "too_large"])
def test_invalid_domains_are_rejected_before_copying_values(violation):
    from apixly_jev_harness.engine import DecisionStop

    class Uncopyable(dict):
        def __deepcopy__(self, memo):
            pytest.fail("invalid domain must be rejected before value cloning")

    count = 2 if violation == "duplicate" else 254
    domain = [
        Option("same" if violation == "duplicate" else str(i), "Value", Uncopyable(value=i))
        for i in range(count)
    ]
    task = Task(observe=lambda ctx: {}, verify=lambda ctx, seen: False)

    @task.tool("Read value", parameters={"value": lambda ctx, seen: domain})
    def read(value):
        return value

    with pytest.raises(
        ValueError if violation == "duplicate" else DecisionStop,
        match="duplicate_option_ids" if violation == "duplicate" else "parameter_domain_too_large",
    ):
        task.candidates(None, {})


@pytest.mark.parametrize("strategy", ["staged", "joint"])
def test_candidate_domain_detaches_mutable_values_from_provider(strategy):
    payload = {"nested": ["synthetic-a"]}
    task = Task(observe=lambda ctx: {}, verify=lambda ctx, seen: False, strategy=strategy)

    @task.tool("Read described record", parameters={"record": lambda ctx, seen: [payload]})
    def read(record):
        return record

    offered = task.candidates(None, {})
    if strategy == "staged":
        action = task.bind(None, {}, offered[0], lambda *args: pytest.fail("singleton inference"))
    else:
        action = offered[0]
    payload["nested"].append("synthetic-b")
    assert task.execute(None, action) == {"nested": ["synthetic-a"]}


def test_uncopyable_unselected_value_fails_before_any_selection(monkeypatch, tmp_path):
    class Uncopyable(dict):
        def __deepcopy__(self, memo):
            raise RuntimeError("synthetic-private-copy-error")

    domain = [
        Option("good", "Copyable value", {"value": "good"}),
        Option("bad", "Uncopyable value", Uncopyable(value="bad")),
    ]
    task = Task(observe=lambda ctx: {}, verify=lambda ctx, seen: False)

    @task.tool("Read selected value", parameters={"value": lambda ctx, seen: domain})
    def read(value):
        pytest.fail("must not execute an unsnapshotted domain")

    monkeypatch.setattr(
        "apixly_jev_harness.engine.analysis.evaluate",
        lambda *args: pytest.fail("must not select an unsnapshotted domain"),
    )
    result = AgentLoop().run(task, goal="Read value", archive=tmp_path / "run.jsonl")
    assert result["status"] == "failed" and result["error_type"] == "RuntimeError"
    assert result["steps"] == result["telemetry"]["requests"] == 0
    assert result["telemetry"]["usage_complete"] is True
    assert "synthetic-private-copy-error" not in json.dumps(result)


def test_machine_contract_describes_per_domain_snapshot_scope():
    from apixly_jev_harness.task_cli import SPEC

    contract = SPEC["parameter_snapshots"]
    assert contract["scope"] == "each_valid_parameter_domain"
    assert contract["stage"] == "after_domain_validation_before_selection"
    assert contract["provider_results_cached"] is False
    assert contract["atomic_acquisition"] is False
