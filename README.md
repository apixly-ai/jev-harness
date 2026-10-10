# Jev Harness

[简体中文](README.zh-CN.md) · [Documentation](https://apixly-ai.github.io/jev-harness/) · [Agent contract](docs/agent-contract.md) · [Evidence](reports/README.md)

**Write a task. Register tools. Let Jev choose the next call and its parameters.**

Jev Harness is a Python runtime for AI-authored, bounded task scripts. It gives Jev the
explicit goal, admitted conversation, current observation, execution history and tool
contracts. Jev chooses a tool and parameter candidates; code executes and independently
verifies completion. Independent community project by Apixly, not an official TypeSafe
AI product. Early **0.1.3**; no promise of general task success or universal savings.

The distribution is **apixly-jev-harness**, the Python namespace is `apixly_jev_harness`,
and `apixly-jev-harness` is an unambiguous CLI alias. Use this repository’s exact Git
installation URL; the PyPI name jev-harness belongs to an unrelated project.

## Start with the agent interface

Python 3.10+ and Git are required. The runtime pins Jev Filter 0.4.1 from GitHub as its
inference and platform dependency. Installation makes no model calls.

```sh
python -m venv .venv
. .venv/bin/activate
pip install 'git+https://github.com/apixly-ai/jev-harness.git@v0.1.3'
jev-harness spec
jev-harness init-task task.py
jev-harness check-task task.py
# Billable: configure TYPESAFE_API_KEY or TYPESAFE_API_KEY_FILE in your environment.
jev-harness run task.py --goal 'Reach the requested target' --inputs '{"target":3}'
```

Use `@main` instead of `@v0.1.3` only for active development.

`check-task` checks syntax/export without executing code; it does not prove callback
correctness. `run` loads caller-trusted Python, not a sandbox. Only `done` exits 0;
exit 2 still returns a terminal JSON packet. Uncertain effects are never auto-retried.

## Define tools and parameter meaning

```python
from apixly_jev_harness import Parameter, Task

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

Tool selection asks for the **next step**. Gathering evidence or satisfying a prerequisite
can advance the task without completing the entire goal in one call. Describe each tool's
preconditions, expected effect and applicable exit or priority rules in the caller's goal
and contracts. The core has no general UI-form ordering rules; candidate position does
not establish priority. The host supplies `decision_stage=tool_selection` or
`parameter_selection` to distinguish loop decisions. Direct `Engine.decide` filtering
without this loop marker retains general candidate-selection semantics. Conditional
parameter binding, authorization, independent verification and exit checks are unchanged.

## Two native interfaces

- **Jev-native:** native Choice answers with probabilities; sequential parameter dependency
  resolution; strict selected-ID binding; abstention and independent completion checks.
- **AI-native:** machine-readable `spec`, a runnable scaffold, offline syntax checking,
  typed Python interfaces and a bundled [agent skill](skills/jev-harness/SKILL.md).
  No hidden hook installation or automatic interception of every agent tool call.

[Context management](docs/context.md) keeps goals/facts/messages, an action ledger,
recent admitted tool results and references to older evidence. Raw evidence stays in
private journals. Budget overflow returns review instead of silently losing constraints.

An admitted tool-result summary can advance the next decision even when the observation
is unchanged. Raw results without `result_context` admission cannot advance that state.
Within one run, the same observation, action ID and actual bound parameters may execute
only once; a repeated invocation stops before execution with `blocked/repeated_action_state`.
Polling the same call against a fixed observation is unsupported. Handle polling inside
a tool with its own bounds, or expose meaningful observed progress.

Unresolved inference may return a host-generated `diagnostic` identifying
`tool_selection` or `parameter_selection`, registered tool/parameter identifiers for
the latter, allowlisted `reason_codes` and `automatic_retry: false`. Each inference
entry in `telemetry.calls` carries its stage and applicable identifiers. The
[contract](docs/agent-contract.md#decision-diagnostics) explains the codes and primary-agent
handoff; exceptions, response bodies and bound values are not exported in diagnostics.
Static domain, policy and execution errors keep their existing terminal reasons.
Diagnostics do not change eligibility, status or authorization. The harness does not
repeat task calls automatically; the pinned SDK's bounded 429/503/529 retries remain,
so this is not a one-network-request guarantee.

Browser and desktop are [tool adapters](docs/adapters.md), not application-specific
programs in the runtime. Camofox uses fresh observed targets and allowed origins;
desktop uses pinned macOS Accessibility/Windows UIA backends. Caller policy authorizes
exact click actions; scripts must own business identity and idempotency.

## Verification, not promises

The `verify_state` helper requires nonempty text or at least one control condition.
Every expected control field must be observed; a missing field does not establish `null`.
The [evidence-progress A/B](reports/evidence-progress-ab.json) uses synthetic offline
decisions to check result-driven continuation and repeated-call blocking. It is not live
model acceptance or evidence of general performance gains.

The [decision-diagnostics A/B](reports/decision-diagnostics-ab.json) uses synthetic
offline HTTP mocks with zero real model calls. It checks actionable codes and stage
metadata; it adds terminal bytes, unknown errors fall back to generic codes, and real
semantic recovery success has not been measured.

[Tool-choice offline A/B](reports/tool-choice-offline-ab.json) and
[tool-choice live A/B](reports/tool-choice-live-ab.json) cover six development synthetic
single-decision cases with normal and reversed candidate order. The probe stops before
intent, so these reports cannot prove full-task, browser or desktop completion. Read the
reports for measured outcomes and usage; no general quality or cost benefit is established.

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
pytest --cov=apixly_jev_harness
python -m build
python scripts/check_public.py
```

See [architecture and references](docs/architecture.md). Live tests are opt-in, billable
and use synthetic/permitted inputs plus an explicitly supplied credential. Contributions
must retain negative results and distinguish mock, live and production evidence.
