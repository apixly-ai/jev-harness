# Jev Harness

[简体中文](README.zh-CN.md) · [Documentation](https://apixly-ai.github.io/jev-harness/) · [Agent contract](docs/agent-contract.md) · [Evidence](reports/README.md)

**Write a task. Register tools. Let Jev choose the next call and its parameters.**

Jev Harness is a Python runtime for AI-authored, bounded task scripts. It gives Jev the
explicit goal, admitted conversation, current observation, execution history and tool
contracts. Jev chooses a tool and parameter candidates; code executes and independently
verifies completion. Independent community project by Apixly, not an official TypeSafe
AI product. Early **0.1.0**; no promise of general task success or universal savings.

## Start with the agent interface

Python 3.10+ and Git are required. The runtime pins Jev Filter 0.4.1 from GitHub as its
inference and platform dependency. Installation makes no model calls.

```sh
python -m venv .venv
. .venv/bin/activate
pip install 'git+https://github.com/apixly-ai/jev-harness.git@main'
jev-harness spec
jev-harness init-task task.py
jev-harness check-task task.py
# Billable: configure TYPESAFE_API_KEY or TYPESAFE_API_KEY_FILE in your environment.
jev-harness run task.py --goal 'Reach the requested target' --inputs '{"target":3}'
```

`check-task` checks syntax/export without executing code; it does not prove callback
correctness. `run` loads caller-trusted Python, not a sandbox. Only `done` exits 0;
exit 2 still returns a terminal JSON packet. Uncertain effects are never auto-retried.

## Define tools and parameter meaning

```python
from jev_harness import Parameter, Task

state = {"value": 0}
workflow = Task(
    observe=lambda ctx: {"value": state["value"], "target": ctx.inputs["target"]},
    verify=lambda ctx, seen: seen["value"] == seen["target"],
)

@workflow.tool("Advance toward target without overshooting", parameters={
    "amount": Parameter("Amount needed for the next increment", lambda ctx, seen:
                        [n for n in (1, 2) if seen["value"] + n <= seen["target"]]),
}, result_context=lambda result: result)
def increment(amount):
    state["value"] += amount
    return {"value": state["value"]}
```

Domains may be static or derived from the observed state. `depends_on` constructs child
candidates only after parent arguments are selected. `Option(id, description, value)`
separates model-visible semantics from the actual bound value. Singleton domains bind
without inference. Parameters are selected from supplied candidates, never invented.

## Two native interfaces

- **Jev-native:** native Choice answers with probabilities; sequential parameter dependency
  resolution; strict selected-ID binding; abstention and independent completion checks.
- **AI-native:** machine-readable `spec`, a runnable scaffold, offline syntax checking,
  typed Python interfaces and a bundled [agent skill](skills/jev-harness/SKILL.md).
  No hidden hook installation or automatic interception of every agent tool call.

[Context management](docs/context.md) keeps goals/facts/messages, an action ledger,
recent admitted tool results and references to older evidence. Raw evidence stays in
private journals. Budget overflow returns review instead of silently losing constraints.

Browser and desktop are [tool adapters](docs/adapters.md), not application-specific
programs in the runtime. Camofox uses fresh observed targets and allowed origins;
desktop uses pinned macOS Accessibility/Windows UIA backends. Caller policy authorizes
exact click actions; scripts must own business identity and idempotency.

## Verification, not promises

A live Jev/Camofox synthetic form reached the independently checked final state in
four tool executions. Early attempts requiring review are retained. Desktop live
acceptance is **not yet proven**: this host is locked; offline adapter tests do not
replace native acceptance. [Exact evidence and limits](reports/README.md).

No result cache. Independent inference concurrency is capped at 30. Synchronous time
budgets are checked between callbacks; tools must bound their own I/O. The runtime
records intent before execution, preserves unknown usage, and does not implement
cross-run resume or exactly-once effects.

## Development

```sh
pip install -e '.[dev]'
ruff check src tests benchmarks scripts
pytest --cov=jev_harness
python -m build
python scripts/check_public.py
```

See [architecture and references](docs/architecture.md). Live tests are opt-in, billable
and use synthetic/permitted inputs plus an explicitly supplied credential. Contributions
must retain negative results and distinguish mock, live and production evidence.
