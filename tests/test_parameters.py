import pytest

from jev_harness import AgentLoop, Option, Parameter, Task


def test_dependent_domains_bound_after_parent_selection(monkeypatch):
    calls = []
    state = {"done": False}
    task = Task(observe=lambda ctx: state.copy(), verify=lambda ctx, state: state["done"])

    @task.tool(
        "Inspect one customer's job",
        parameters={
            "customer": Parameter("Which customer owns the failed job?", ["alice", "bob"]),
            "job": Parameter(
                "Job belonging to the selected customer",
                lambda ctx, state, bound: [
                    Option("current", "Current failed job", bound["customer"] + "-1")
                ],
                depends_on=("customer",),
            ),
        },
    )
    def inspect(customer, job):
        calls.append((customer, job))
        state["done"] = True

    def choose(parts, goal, workers, spec):
        selected = parts[-1]["id"] if "customer" in goal else parts[0]["id"]
        return {
            p["id"]: {"status": "OK", "decision": "MATCH" if p["id"] == selected else "EXCLUDE"}
            for p in parts
        }, {
            "ok": True,
            "usage_complete": True,
            "usage": {"input_tokens": 5, "output_tokens": 1},
            "requests": 1,
        }

    monkeypatch.setattr("jev_harness.engine.analysis.evaluate", choose)
    result = AgentLoop().run(task, goal="Inspect Bob's current failed job")
    assert result["status"] == "done"
    assert calls == [("bob", "bob-1")]
    assert result["telemetry"]["requests"] == 2  # tool + non-singleton parameter


def test_large_joint_space_does_not_expand_cartesian_product():
    task = Task(observe=lambda ctx: {}, verify=lambda ctx, state: False)

    @task.tool(
        "Choose two values",
        parameters={
            "a": Parameter("First", list(range(100))),
            "b": Parameter("Second", list(range(100))),
        },
    )
    def choose(a, b):
        pass

    assert len(task.candidates(None, {})) == 1


def test_parameter_dependencies_must_be_acyclic():
    task = Task(observe=lambda ctx: {}, verify=lambda ctx, state: False)
    with pytest.raises(ValueError, match="depend"):
        task.tool(
            "Invalid",
            parameters={
                "a": Parameter("A", [1], depends_on=("b",)),
                "b": Parameter("B", [1], depends_on=("a",)),
            },
        )(lambda a, b: None)
