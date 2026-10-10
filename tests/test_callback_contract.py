import functools
import json
import threading

import pytest

from apixly_jev_harness import Action, AgentLoop, Parameter, Task, Workflow
from apixly_jev_harness.callbacks import CallbackContractError, project_contract_error
from apixly_jev_harness.task_cli import main


async def async_callback(*args):
    raise AssertionError("Deferred callback body must not run")


def generator_callback(*args):
    raise AssertionError("Deferred callback body must not run")
    yield 1


async def async_generator_callback(*args):
    raise AssertionError("Deferred callback body must not run")
    yield 1


async def async_effect():
    raise AssertionError("Must not run")


def generator_effect():
    raise AssertionError("Must not run")
    yield 1


async def async_generator_effect():
    raise AssertionError("Must not run")
    yield 1


@pytest.mark.parametrize("role", ["observe", "verify", "authorize"])
def test_task_rejects_declared_async_callbacks_at_construction(role):
    kwargs = {"observe": lambda ctx: {}, "verify": lambda ctx, state: False, role: async_callback}
    with pytest.raises(ValueError, match="synchronous_callback_required"):
        Task(**kwargs)


@pytest.mark.parametrize("callback", [async_effect, generator_effect, async_generator_effect])
def test_tool_rejects_deferred_execution_before_registration(callback):
    task = Task(observe=lambda ctx: {}, verify=lambda ctx, seen: False)
    with pytest.raises(ValueError, match="synchronous_callback_required"):
        task.tool("Deferred effect", name="effect")(callback)
    assert task.describe() == {}


@pytest.mark.parametrize("role", ["available", "result_context"])
def test_tool_rejects_async_metadata_callbacks(role):
    task = Task(observe=lambda ctx: {}, verify=lambda ctx, seen: False)
    with pytest.raises(ValueError, match="synchronous_callback_required"):
        task.tool("Inspect", **{role: async_callback})(lambda: None)


@pytest.mark.parametrize(
    "callback", [async_callback, generator_callback, functools.partial(async_callback, "fixed")]
)
def test_parameter_rejects_known_deferred_providers(callback):
    with pytest.raises(ValueError, match="synchronous_callback_required"):
        Parameter("Observed choices", callback)


def test_async_callable_object_is_rejected_without_calling_it():
    class AsyncObserver:
        async def __call__(self, ctx):
            raise AssertionError("Must not run")

    with pytest.raises(ValueError, match="synchronous_callback_required"):
        Task(observe=AsyncObserver(), verify=lambda ctx, state: False)


@pytest.mark.parametrize("kind", ["coroutine", "generator", "async_generator"])
def test_partial_deferred_callable_objects_are_rejected_without_calling_them(kind):
    class AsyncProvider:
        async def __call__(self, prefix, ctx, state):
            raise AssertionError("Must not run")

    class GeneratorProvider:
        def __call__(self, prefix, ctx, state):
            raise AssertionError("Must not run")
            yield prefix

    class AsyncGeneratorProvider:
        async def __call__(self, prefix, ctx, state):
            raise AssertionError("Must not run")
            yield prefix

    providers = {
        "coroutine": AsyncProvider,
        "generator": GeneratorProvider,
        "async_generator": AsyncGeneratorProvider,
    }
    provider = functools.partial(functools.partial(providers[kind](), "fixed"))
    with pytest.raises(ValueError, match="synchronous_callback_required") as failure:
        Parameter("Observed choices", provider)
    assert failure.value.kind == kind


def test_tool_preserves_dynamic_provider_identity_and_snapshots_static_choices():
    class Provider:
        def __init__(self):
            self.lock = threading.Lock()
            self.calls = 0

        def __call__(self, prefix, ctx, state):
            with self.lock:
                self.calls += 1
                return [prefix]

    owner = Provider()
    provider = functools.partial(owner, "dynamic")
    static_choices = [{"value": "original"}]
    task = Task(observe=lambda ctx: {}, verify=lambda ctx, state: False)

    @task.tool(
        "Inspect",
        parameters={
            "dynamic": Parameter("Dynamic choice", provider),
            "static": Parameter("Static choice", static_choices),
        },
    )
    def inspect(dynamic, static):
        return dynamic, static

    assert task._tools["inspect"]["parameters"]["dynamic"].choices is provider
    assert owner.calls == 0
    static_choices[0]["value"] = "changed"
    offered = task.candidates(None, {})
    action = task.bind(None, {}, offered[0], lambda *args: pytest.fail("Singletons"))
    assert task.execute(None, action) == ("dynamic", {"value": "original"})
    assert owner.calls == 2  # Fresh domains for offering and binding; no result cache.


def test_provider_with_optional_keyword_argument_receives_bound_parents():
    def provider(ctx, state, bound, *, suffix="child"):
        return [bound["parent"] + "-" + suffix]

    task = Task(observe=lambda ctx: {}, verify=lambda ctx, state: False)

    @task.tool(
        "Inspect",
        parameters={
            "parent": ["A"],
            "target": Parameter("Child", provider, depends_on=("parent",)),
        },
    )
    def inspect(parent, target):
        return target

    offered = task.candidates(None, {})
    action = task.bind(
        None, {}, offered[0], lambda *args: pytest.fail("Singletons need no inference")
    )
    assert task.execute(None, action) == "A-child"


def test_unsupported_provider_signature_is_rejected_without_invocation():
    def provider(ctx, state, *, required):
        raise AssertionError("Must not run")

    with pytest.raises(ValueError, match="provider_signature_unsupported"):
        Parameter("Observed choices", provider)


def test_custom_async_workflow_is_rejected_before_observation_or_journal(tmp_path):
    observed = []

    class AsyncWorkflow(Workflow):
        def observe(self, ctx):
            observed.append(1)
            return {}

        async def execute(self, ctx, action):
            raise AssertionError("Must not run")

    with pytest.raises(ValueError, match="synchronous_callback_required"):
        AgentLoop().run(AsyncWorkflow(), goal="Inspect", archive=tmp_path / "run.jsonl")
    assert observed == []
    assert not (tmp_path / "run.jsonl").exists()


def test_async_context_policy_is_rejected_before_observation_or_journal(tmp_path):
    observed = []

    class AsyncPolicy:
        async def build(self, *args):
            raise AssertionError("Must not run")

    task = Task(observe=lambda ctx: observed.append(1), verify=lambda ctx, state: False)
    with pytest.raises(CallbackContractError) as failure:
        AgentLoop().run(
            task, goal="Inspect", context_policy=AsyncPolicy(), archive=tmp_path / "run.jsonl"
        )
    assert failure.value.callback == "context_policy"
    assert observed == []
    assert not (tmp_path / "run.jsonl").exists()


def test_contract_error_during_effect_remains_uncertain_and_is_not_retried(monkeypatch, tmp_path):
    effects = []
    task = Task(observe=lambda ctx: {}, verify=lambda ctx, state: False)

    @task.tool("Inspect")
    def inspect():
        effects.append(1)
        raise CallbackContractError("provider_signature_unsupported", "choices")

    def choose(parts, *args):
        return {
            part["id"]: {"status": "OK", "decision": "MATCH" if i == 0 else "EXCLUDE"}
            for i, part in enumerate(parts)
        }, {"ok": True, "usage_complete": True, "usage": {"input_tokens": 0, "output_tokens": 0}}

    monkeypatch.setattr("apixly_jev_harness.engine.analysis.evaluate", choose)
    result = AgentLoop().run(task, goal="Inspect", archive=tmp_path / "run.jsonl")
    assert result["status"] == "execution_uncertain"
    assert result["action_id"] == "inspect"
    assert result["contract_error"] == {
        "code": "provider_signature_unsupported",
        "callback": "choices",
    }
    assert effects == [1]


def test_contract_diagnostic_projects_only_fixed_enums():
    error = CallbackContractError("synchronous_callback_required", "observe", "coroutine")
    error.code, error.callback, error.kind = ["PRIVATE"], "PRIVATE", {"PRIVATE": 1}
    assert project_contract_error(error) == {"code": "callback_contract_error"}


def test_cli_reports_safe_callback_role_and_kind(tmp_path, capsys, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Unit fixture must not invoke inference")

    monkeypatch.setattr("apixly_jev_harness.backend.native_run", forbidden)
    script = tmp_path / "task.py"
    script.write_text(
        "from apixly_jev_harness import Task\nworkflow=Task(observe=lambda ctx: {}, verify=lambda ctx, state: False)\n@workflow.tool('Inspect')\nasync def inspect():\n    raise RuntimeError('PRIVATE_CALLBACK_TEXT')\n"
    )
    assert main(["run", str(script), "--goal", "Inspect"]) == 2
    packet = json.loads(capsys.readouterr().out)
    assert packet["contract_error"] == {
        "code": "synchronous_callback_required",
        "callback": "execute",
        "kind": "coroutine",
    }
    assert "PRIVATE_CALLBACK_TEXT" not in json.dumps(packet)


def test_generator_candidates_and_synchronous_bridges_remain_supported(monkeypatch, tmp_path):
    done = []

    class GeneratorCandidates(Workflow):
        def observe(self, ctx):
            return {"done": bool(done)}

        def verify(self, ctx, state):
            return state["done"]

        def candidates(self, ctx, state):
            yield Action("inspect", "Inspect")

        def execute(self, ctx, action):
            done.append(1)

    def choose(parts, *args):
        return {
            part["id"]: {"status": "OK", "decision": "MATCH" if i == 0 else "EXCLUDE"}
            for i, part in enumerate(parts)
        }, {"ok": True, "usage_complete": True, "usage": {"input_tokens": 0, "output_tokens": 0}}

    monkeypatch.setattr("apixly_jev_harness.engine.analysis.evaluate", choose)
    assert (
        AgentLoop().run(GeneratorCandidates(), goal="Inspect", archive=tmp_path / "run.jsonl")[
            "status"
        ]
        == "done"
    )

    @functools.wraps(async_callback)
    def bridge(ctx):
        return {}

    assert Task(observe=bridge, verify=lambda ctx, state: True).observe(None) == {}
