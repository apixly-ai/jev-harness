import functools
import inspect
import json

import pytest

from apixly_jev_harness import AgentLoop, Option, Parameter, Task
from apixly_jev_harness.callbacks import CallbackContractError, provider_arity
from apixly_jev_harness.task_cli import SPEC, main


def providers(kind):
    called = []

    def two(ctx, state):
        called.append(2)
        return [Option("current", "Current object", "PRIVATE_CURRENT")]

    def three(ctx, state, bound):
        called.append(3)
        return [Option("current", "Current child", bound["parent"] + "-child")]

    async def async_two(ctx, state):
        raise AssertionError("Wrapped async declaration must not be called")

    if kind == "three_wraps_two":
        return functools.wraps(two)(three), called, 3
    if kind == "two_wraps_three":
        return functools.wraps(three)(two), called, 2
    if kind == "three_wraps_async":
        return functools.wraps(async_two)(three), called, 3
    if kind in ("optional_three_wraps_two", "variadic_three_wraps_two"):
        if kind == "optional_three_wraps_two":

            @functools.wraps(two)
            def optional(ctx, state, bound=None):
                return three(ctx, state, bound) if bound is not None else []
        else:

            @functools.wraps(two)
            def optional(ctx, state, bound=None, *args):
                return three(ctx, state, bound) if bound is not None else []

        return optional, called, 3
    if kind == "partial_bridge":

        @functools.wraps(two)
        def bridge(prefix, ctx, state, bound):
            return three(ctx, state, bound)

        return functools.partial(bridge, "fixed"), called, 3
    if kind in ("callable_bridge", "partial_callable_bridge"):

        class Bridge:
            @functools.wraps(async_two)
            def __call__(self, ctx, state, bound):
                return three(ctx, state, bound)

        owner = Bridge()
        return functools.partial(owner) if kind.startswith("partial") else owner, called, 3
    if kind in ("transparent_two", "partial_transparent_two", "transparent_three"):
        delegate = three if kind == "transparent_three" else two

        @functools.wraps(delegate)
        def forward(*args, **kwargs):
            return delegate(*args, **kwargs)

        return (
            functools.partial(forward) if kind.startswith("partial") else forward,
            called,
            (3 if kind == "transparent_three" else 2),
        )
    if kind == "explicit_signature":

        @functools.wraps(three)
        def forward(*args, **kwargs):
            return two(*args, **kwargs)

        forward.__signature__ = inspect.signature(two)
        return forward, called, 2
    return (two, called, 2) if kind == "plain_two" else (three, called, 3)


@pytest.mark.parametrize(
    "kind",
    [
        "three_wraps_two",
        "two_wraps_three",
        "three_wraps_async",
        "optional_three_wraps_two",
        "variadic_three_wraps_two",
        "partial_bridge",
        "callable_bridge",
        "partial_callable_bridge",
        "transparent_two",
        "partial_transparent_two",
        "transparent_three",
        "explicit_signature",
        "plain_two",
        "plain_three",
    ],
)
def test_provider_uses_supported_outer_or_transparent_contract_without_invoking_on_admission(
    monkeypatch, tmp_path, kind
):
    provider, calls, arity = providers(kind)
    dependent = arity == 3
    spec = Parameter(
        "Current observed object", provider, depends_on=("parent",) if dependent else ()
    )
    task_calls = []
    state = {"done": False}
    task = Task(observe=lambda ctx: dict(state), verify=lambda ctx, seen: seen["done"])

    @task.tool(
        "Synthetic tool",
        parameters={
            **(
                {"parent": [Option("parent", "Current parent", "PRIVATE_PARENT")]}
                if dependent
                else {}
            ),
            "target": spec,
        },
    )
    def effect(target, parent=None):
        expected = "PRIVATE_PARENT-child" if dependent else "PRIVATE_CURRENT"
        task_calls.append(target)
        state["done"] = target == expected

    assert calls == []
    assert task._tools["effect"]["parameters"]["target"].choices is provider

    def choose(parts, goal, workers, spec):
        assert "PRIVATE_" not in json.dumps([parts, spec])
        return {
            part["id"]: {"status": "OK", "decision": "MATCH" if i == 0 else "EXCLUDE"}
            for i, part in enumerate(parts)
        }, {"ok": True, "requests": 1, "usage_complete": False, "usage": None}

    monkeypatch.setattr("apixly_jev_harness.engine.analysis.evaluate", choose)

    def forbidden(*args, **kwargs):
        raise AssertionError("No real inference in callback fixture")

    monkeypatch.setattr("apixly_jev_harness.backend.native_run", forbidden)
    result = AgentLoop().run(
        task, goal="Synthetic goal", archive=tmp_path / "run.jsonl", max_steps=1
    )
    assert result["status"] == "done" and len(task_calls) == 1
    assert provider_arity(provider) == arity
    assert calls == [arity] * (1 if dependent else 2)
    assert result["telemetry"]["usage"] is None


def test_outer_four_required_arguments_are_rejected_despite_wrapped_two():
    def declaration(ctx, state):
        raise AssertionError("Metadata declaration must not run")

    @functools.wraps(declaration)
    def actual(prefix, ctx, state, bound):
        raise AssertionError("Invalid callback must not run")

    with pytest.raises(CallbackContractError) as error:
        Parameter("Observed object", actual)
    assert error.value.code == "provider_signature_unsupported"


def test_signature_admission_still_does_not_prove_callback_body_behavior():
    called = []

    def forward(*args):
        called.append(1)
        raise TypeError("PRIVATE_BODY_FAILURE")

    forward.__signature__ = inspect.Signature(
        [
            inspect.Parameter("ctx", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            inspect.Parameter("state", inspect.Parameter.POSITIONAL_OR_KEYWORD),
        ]
    )
    assert provider_arity(forward) == 2 and called == []
    with pytest.raises(TypeError, match="PRIVATE_BODY_FAILURE"):
        forward(None, {})
    assert called == [1]


def test_spec_explains_provider_signature_selection_and_proof_limits():
    contract = SPEC["callbacks"]
    assert contract["provider_outer_signature"] == "inspect.signature(follow_wrapped=False)"
    assert contract["provider_generic_wrapped_contract"] == "advertised signature and actual bind"
    assert contract["provider_explicit_signature_override"] == "respected; does not prove behavior"


def test_cli_decorated_dependent_provider_receives_selected_parent(monkeypatch, tmp_path, capsys):
    def choose(parts, *args):
        return {
            part["id"]: {"status": "OK", "decision": "MATCH" if i == 0 else "EXCLUDE"}
            for i, part in enumerate(parts)
        }, {"ok": True, "requests": 1, "usage_complete": False, "usage": None}

    monkeypatch.setattr("apixly_jev_harness.engine.analysis.evaluate", choose)
    script = tmp_path / "task.py"
    script.write_text(
        "import functools\n"
        "from apixly_jev_harness import Option,Parameter,Task\n"
        "state={'done':False}\n"
        "async def declaration(ctx,seen):\n"
        "    raise AssertionError('Must not run')\n"
        "@functools.wraps(declaration)\n"
        "def choices(ctx,seen,bound):\n"
        "    return [Option('child','Current child',bound['parent']+'-child')]\n"
        "workflow=Task(observe=lambda ctx:dict(state),verify=lambda ctx,seen:seen['done'])\n"
        "@workflow.tool('Synthetic call',parameters={'parent':[Option('parent','Current parent','PRIVATE_PARENT')],"
        "'target':Parameter('Current child',choices,depends_on=('parent',))})\n"
        "def effect(parent,target):\n"
        "    state['done']=target==parent+'-child'\n"
    )
    assert main(["run", str(script), "--goal", "Synthetic goal"]) == 0
    captured = capsys.readouterr()
    packet = json.loads(captured.out)
    assert packet["status"] == "done" and packet["steps"] == 1
    assert packet["telemetry"]["requests"] == 1 and packet["telemetry"]["usage"] is None
    assert packet["telemetry"]["owned_transport"]["request_attempts"] == 0
    assert captured.err == "" and "PRIVATE_PARENT" not in captured.out
