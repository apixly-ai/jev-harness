import io
import json

import pytest

from apixly_jev_harness import Task
from apixly_jev_harness.mcp import serve
from apixly_jev_harness.toolkit import ToolkitSession


def session():
    state = {"value": 0}
    task = Task(observe=lambda c: dict(state), verify=lambda c, s: s["value"] == 2)

    @task.tool("Advance the value", parameters={"amount": [1, 2]}, result_context=lambda x: x)
    def advance(amount):
        state["value"] += amount
        return dict(state)

    return ToolkitSession(task, goal="Reach two", max_steps=4), state


def test_direct_calls_bind_only_current_refs_and_need_no_jev():
    client, state = session()
    seen = client.observe()
    assert seen["tools"][0]["tool"] == "advance"
    with pytest.raises(ValueError):
        client.operate("advance", {"amount": "invented"})
    assert state["value"] == 0
    reply = client.operate("advance", {"amount": "1"})
    assert reply["complete"] is True and state["value"] == 2
    assert client.steps == 1


def test_stale_state_and_invalid_arguments_do_not_execute():
    client, state = session()
    client.observe()
    state["value"] = 1
    with pytest.raises(ValueError, match="stale"):
        client.operate("advance", {"amount": "0"})
    assert state["value"] == 1
    client.observe()
    for args in [{"amount": True}, {"amount": "0", "other": "x"}]:
        with pytest.raises(ValueError):
            client.operate("advance", args)
    assert state["value"] == 1


def test_mcp_supports_both_routes_without_preferring_either():
    client, state = session()
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "observe", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "operate",
                "arguments": {
                    "tool": "advance",
                    "parameters": {"amount": "1"},
                    "state_ref": client.observe()["state_ref"],
                },
            },
        },
    ]
    out = io.StringIO()
    serve(
        client,
        source=io.StringIO("\n".join(json.dumps(x) for x in requests) + "\n"),
        destination=out,
    )
    replies = [json.loads(x) for x in out.getvalue().splitlines()]
    assert len(replies) == 4
    names = {x["name"] for x in replies[1]["result"]["tools"]}
    assert names == {"observe", "arguments", "operate", "run_task"}
    assert json.loads(replies[-1]["result"]["content"][0]["text"])["complete"] is True
    assert state["value"] == 2


def test_direct_only_server_does_not_expose_delegation():
    client, _ = session()
    source = io.StringIO(json.dumps({"id": 1, "method": "tools/list"}) + "\n")
    out = io.StringIO()
    serve(client, source=source, destination=out, allow_delegate=False)
    names = {x["name"] for x in json.loads(out.getvalue())["result"]["tools"]}
    assert names == {"observe", "arguments", "operate"}


def test_thin_script_factory_receives_runtime_inputs_once():
    from apixly_jev_harness.toolkit import TaskScript

    builds = []

    def build(inputs):
        builds.append(dict(inputs))
        task, _ = session()
        return task.task

    script = TaskScript(build)
    assert builds == []
    client = ToolkitSession(script, goal="Reach two", inputs={"root": "caller-owned"})
    client.observe()
    client.observe()
    assert builds == [{"root": "caller-owned"}]
    assert client.operate("advance", {"amount": "1"})["complete"] is True


def test_invalid_rpc_does_not_reuse_previous_request_identity():
    client, _ = session()
    out = io.StringIO()
    serve(client, source=io.StringIO('{"id":9,"method":"ping"}\n{broken\n'), destination=out)
    rows = [json.loads(x) for x in out.getvalue().splitlines()]
    assert rows[1]["id"] is None
    assert rows[1]["error"]["code"] == -32600


def test_server_observation_does_not_lose_fact_requiring_dependency_first():
    from apixly_jev_harness import Option, Parameter

    state = {"done": False}
    task = Task(observe=lambda c: dict(state), verify=lambda c, s: s["done"])

    @task.tool(
        "Read a selected resource field",
        parameters={
            "resource": [Option("a", "Resource A", "resource-a")],
            "field": Parameter(
                "Field belonging to chosen resource",
                lambda c, s, b: [Option("state", "Resource state", "state")],
                depends_on=("resource",),
            ),
        },
    )
    def read(resource, field):
        state["done"] = True
        return {"resource": resource, "field": field}

    client = ToolkitSession(task, goal="Read state")
    client.observe()
    assert client.operate("read", {"resource": "a", "field": "state"})["complete"] is True


def test_direct_does_not_reacquire_parameter_provider_or_accept_joint():
    calls = []
    state = {"done": False}
    task = Task(observe=lambda c: dict(state), verify=lambda c, s: s["done"])

    @task.tool("Read", parameters={"value": lambda c, s: calls.append(1) or [1, 2]})
    def read(value):
        state["done"] = True

    client = ToolkitSession(task, goal="Read")
    client.observe()
    calls.clear()
    client.operate("read", {"value": "0"})
    assert len(calls) == 1
    with pytest.raises(ValueError, match="staged"):
        ToolkitSession(
            Task(observe=lambda c: {}, verify=lambda c, s: False, strategy="joint"), goal="Read"
        )


def test_resolve_exposes_child_refs_and_route_cannot_switch_after_an_effect():
    from apixly_jev_harness import Option, Parameter

    t = Task(observe=lambda c: {}, verify=lambda c, s: False)

    @t.tool(
        "Inspect",
        parameters={
            "parent": [Option("root", "Root", "root")],
            "child": Parameter(
                "Child of parent",
                lambda c, s, b: [Option("new-child", "New child", 3)],
                depends_on=("parent",),
            ),
        },
    )
    def inspect(parent, child):
        return {"read": child}

    c = ToolkitSession(t, goal="Inspect")
    c.observe()
    resolved = c.resolve("inspect", {"parent": "root"})
    assert resolved["parameters"]["child"]["choices"][0]["id"] == "new-child"
    c.operate("inspect", {"parent": "root", "child": "new-child"})
    with pytest.raises(ValueError, match="after_direct"):
        c.delegate()


def test_ready_task_contract_and_artifact_receipt_are_visible_before_choice(tmp_path):
    from apixly_jev_harness import EvidenceStore, EvidenceTask

    store = EvidenceStore()
    task = EvidenceTask(
        [], store=store, labels=["fact"], output=tmp_path / "out.json", verify=lambda c, s: False
    )
    client = ToolkitSession(task, goal="Investigate")
    info = client.observe()["delegation"]
    assert info["ready"] is True and info["goal"] == "Investigate"
    assert info["artifact"]["path"] == str(tmp_path / "out.json")
    assert info["artifact"]["exists"] is False


def test_direct_cannot_resume_after_delegation_without_guard_transfer(monkeypatch):
    from apixly_jev_harness import AgentLoop

    c, _ = session()
    c.observe()
    monkeypatch.setattr(
        AgentLoop, "run", lambda *a, **k: {"status": "needs_review", "complete": False, "steps": 1}
    )
    c.delegate()
    c.observe()
    with pytest.raises(ValueError, match="after_delegation"):
        c.operate("advance", {"amount": "0"})


def test_direct_verifier_requires_builtin_boolean():
    task = Task(observe=lambda c: {}, verify=lambda c, s: 1)
    c = ToolkitSession(task, goal="Inspect")
    with pytest.raises(ValueError, match="bool"):
        c.observe()


def test_expired_session_does_not_materialize_or_resolve_providers():
    from apixly_jev_harness import TaskScript

    calls = []

    def build(inputs):
        calls.append("build")
        return Task(observe=lambda c: {}, verify=lambda c, s: False)

    c = ToolkitSession(TaskScript(build), goal="Inspect", timeout_seconds=1)
    c._started -= 2
    with pytest.raises(ValueError, match="budget"):
        c.observe()
    assert calls == []


def test_provider_that_exhausts_budget_does_not_execute():
    task = Task(observe=lambda c: {}, verify=lambda c, s: False)
    effects = []
    exhausted = [False]

    def options(c, s):
        if exhausted[0]:
            client._started -= 2
        return [1]

    @task.tool("Read", parameters={"value": options})
    def read(value):
        effects.append(value)

    client = ToolkitSession(task, goal="Read", timeout_seconds=1)
    client.observe()
    exhausted[0] = True
    with pytest.raises(ValueError, match="budget"):
        client.operate("read", {"value": "0"})
    assert effects == []


def test_uncertain_effect_never_advertises_ready_delegation_or_direct_tools():
    task = Task(observe=lambda c: {}, verify=lambda c, s: False)

    @task.tool("Inspect")
    def inspect():
        raise RuntimeError("external effect outcome not established")

    client = ToolkitSession(task, goal="Inspect")
    client.observe()
    with pytest.raises(RuntimeError):
        client.operate("inspect", {})
    state = client.observe()
    assert state["delegation_available"] is False
    assert state["delegation"]["ready"] is False
    assert state["tools"] == []


def test_first_call_delegation_for_lazy_script_returns_real_artifact_receipt(tmp_path, monkeypatch):
    from apixly_jev_harness import AgentLoop, EvidenceStore, EvidenceTask, TaskScript

    def build(inputs):
        return EvidenceTask(
            [],
            store=EvidenceStore(),
            labels=["fact"],
            output=inputs["output"],
            verify=lambda c, s: False,
        )

    workflow = TaskScript(build)
    client = ToolkitSession(workflow, goal="Inspect", inputs={"output": str(tmp_path / "out.json")})

    def run(loop, task, **kwargs):
        # Same materialization timing as the real engine; there was no prior observe.
        task.observe(client.ctx)
        workflow._task.save_report()
        return {"status": "needs_review", "complete": False, "steps": 1}

    monkeypatch.setattr(AgentLoop, "run", run)
    result = client.delegate()
    assert result["artifact"]["path"] == str(tmp_path / "out.json")
    assert result["artifact"]["exists"] is True
    assert result["artifact"]["matches_records"] is True
    assert result["artifact"]["record_count"] == 0


def test_delegate_preserves_engine_context_for_followup_observation(monkeypatch):
    from apixly_jev_harness import AgentLoop, Context, TaskScript

    workflow = TaskScript(
        lambda inputs: Task(
            observe=lambda c: {"count": len(c.results)}, verify=lambda c, s: s["count"] == 1
        )
    )
    client = ToolkitSession(workflow, goal="Inspect")
    actual = Context(goal="Inspect", inputs={}, facts={}, messages=[])

    def run(loop, task, **kwargs):
        task.observe(actual)
        actual.results.append({"action_id": "read", "result": {"found": True}})
        actual.step = 1
        return {"status": "done", "complete": True, "steps": 1}

    monkeypatch.setattr(AgentLoop, "run", run)
    client.delegate()
    observed = client.observe()
    assert observed["observation"]["count"] == 1
    assert observed["complete"] is True
    assert client.ctx is actual


def test_first_delegate_rejects_lazy_joint_task_before_model_or_effect(monkeypatch):
    from apixly_jev_harness import Engine, TaskScript

    model_calls = []

    def forbidden(*a, **k):
        model_calls.append(1)
        raise AssertionError("No inference is permitted in this regression")

    monkeypatch.setattr(Engine, "decide", forbidden)
    effects = []
    task = Task(observe=lambda c: {}, verify=lambda c, s: False, strategy="joint")

    @task.tool("Read")
    def read():
        effects.append(1)

    client = ToolkitSession(TaskScript(lambda inputs: task), goal="Inspect")
    result = client.delegate()
    assert result["status"] == "failed"
    assert result["telemetry"]["requests"] == 0
    assert effects == []
    assert model_calls == []


def test_delegation_proxy_does_not_hide_asynchronous_callback_kind(monkeypatch):
    from apixly_jev_harness import Engine, TaskScript

    bodies = []

    class AsyncTask(Task):
        async def observe(self, ctx):
            bodies.append(1)
            return {}

    def forbidden(*a, **k):
        raise AssertionError("No inference allowed")

    monkeypatch.setattr(Engine, "decide", forbidden)
    task = AsyncTask(observe=lambda c: {}, verify=lambda c, s: False)
    client = ToolkitSession(TaskScript(lambda inputs: task), goal="Inspect")
    result = client.delegate()
    assert result["status"] == "failed"
    assert result["contract_error"]["callback"] == "observe"
    assert result["telemetry"]["requests"] == 0
    assert bodies == []
