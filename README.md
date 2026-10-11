<p><img src="web/brand/hero.svg" width="1200" alt="Jev Harness: your tools, Jev’s next move. Observe, choose, execute and verify."></p>

# Jev Harness

[简体中文](README.zh-CN.md) · [Documentation](https://apixly-ai.github.io/jev-harness/) · [FAQ](docs/faq.md) · [Use cases](docs/use-cases.md) · [Agent contract](docs/agent-contract.md) · [Evidence](reports/README.md)

**Write a task. Register tools. Let Jev choose the next call and its parameters.**

Jev Harness is a Python runtime for AI-authored, bounded task scripts. It gives Jev the
explicit goal, admitted conversation, current observation, execution history and tool
contracts. Jev chooses a tool and parameter candidates; code executes and independently
verifies completion. Independent community project by Apixly, not an official TypeSafe
AI product. Early **0.1.9**; no promise of general task success or universal savings.

The distribution is **apixly-jev-harness**, the Python namespace is `apixly_jev_harness`,
and `apixly-jev-harness` is an unambiguous CLI alias. Use this repository’s exact Git
installation URL; the PyPI name jev-harness belongs to an unrelated project.

## See the loop in action

[Interactive homepage & video](https://apixly-ai.github.io/jev-harness/#showcase) · [Download MP4 replay](web/media/browser-demo.mp4)

[![A blank travel form becomes an independently checked draft: Mira, London, flexible dates](web/media/browser-demo.gif)](https://apixly-ai.github.io/jev-harness/#showcase)

This is a **screenshot replay** captured by headless Camofox from the original local
fixture, with no new model calls. Historical v0.1.0 live Jev acceptance reached the final
state in four tool executions; the replay is labeled separately and is not a newly
recorded inference run. Synthetic data; no real bookings or messages.
[Acceptance ledger](reports/README.md) · [Media scope](web/media/README.md)

| Use case | Inputs and choices | Independent check |
| --- | --- | --- |
| Browser travel draft | Mira, London, flexible dates; observed controls and supplied values | Read field values and final draft text |
| Python tools and parameters | Target 3; increment choices 1 or 2 from current state | Observed value reaches target; historical live scaffold acceptance is in the ledger |
| Evidence progress and execution bounds | Observation, admitted results and action ledger | Offline contracts check continuation, review and repeated-action blocking |

<p><img src="web/brand/workflow.svg" width="1200" alt="The program supplies goals, observations and candidates; Jev selects references; code executes; an independent verifier checks the outcome."></p>

Browser and desktop adapters can host your own task tools. **Native desktop completion
remains unverified.** Each task script supplies its inputs, argument candidates and
completion checks. Code and guard visuals on the homepage are labeled as illustrations
or offline cases.

## Start with the agent interface

Python 3.10+ and Git are required. The runtime pins Jev Filter 0.4.1 from GitHub as its
inference and platform dependency. Installation makes no model calls.

```sh
python -m venv .venv
. .venv/bin/activate
pip install 'git+https://github.com/apixly-ai/jev-harness.git@v0.1.9'
jev-harness spec
jev-harness init-task task.py
jev-harness check-task task.py
# Billable: configure TYPESAFE_API_KEY or TYPESAFE_API_KEY_FILE in your environment.
jev-harness run task.py --goal 'Reach the requested target' --inputs '{"target":3}'
```

Use `@main` instead of `@v0.1.9` only for active development.

When any command's argument parser reports an error, the CLI returns a fixed
`failed/arguments/invalid_command_arguments` packet and exits 2, with
`script_loaded: false` and `model_calls: 0`. Raw argument values, detailed error text and
usage are omitted, so use `spec`/help to correct the command rather than treating this
as tool failure. Valid help remains human text with exit 0 and its original precedence;
it may precede a later unknown-argument check. Valid long-option abbreviations are
unchanged. See the [argument contract](docs/agent-contract.md#cli-argument-parsing) and
[offline A/B](reports/cli-arguments-ab.json).

`check-task` reads UTF-8, parses and compiles Python, and requires an explicit top-level
assignment to `workflow`; `workflow: object` alone does not bind it. It never executes the
script, loads its module, imports its dependencies or invokes callbacks. Passing does not
prove runtime validity or compatibility with another Python version or warning policy.
See the [static-check contract](docs/agent-contract.md#static-task-checking) and
[offline A/B](reports/static-check-ab.json), which executes no checked scripts and uses
zero models or real UI.

`run` validates JSON inputs/context/messages, goal, bounds and required-context path syntax
before creating or loading the task module. CLI inputs/context must be JSON objects and
messages a JSON list; explicit `null` is rejected. Only omitted/`None` Python API
inputs/context/messages receive defaults. Goal and these fields must serialize as finite JSON and encode as UTF-8;
isolated surrogates are rejected. Invalid configuration returns
`failed/configuration/invalid_run_configuration`, with `script_loaded: false` and
`model_calls: 0`. Valid configuration still imports trusted Python, which can have
top-level effects; this preflight is not a sandbox or runtime-validity check. See the
[preflight contract](docs/agent-contract.md#run-configuration-preflight) and
[offline A/B](reports/run-preflight-ab.json), using synthetic import markers and model-free workflows,
with no actual API or UI calls. Returned runtime packets exit 0 only for `done`, otherwise 2.
Uncertain effects are never auto-retried.

During trusted module creation/import and the loop, CLI `run` discards writes to its
redirected Python stdout/stderr without retaining content. Optional `task_output` reports
only Unicode-character and binary-buffer byte counts; it cannot recover discarded debug
text. Return tool results rather than printing them. This output policy applies only to
`run`; `Engine.run` is unchanged. Redirection is process-global: old stream-bound logging handlers, file
descriptors and subprocess output can bypass it, and concurrent thread output is not
isolated. This is neither a sandbox nor a guarantee that all output is private or valid
JSON. Task-path `SystemExit`/`KeyboardInterrupt` restore streams and become quiet nonzero
CLI exits, with no terminal packet or output counts; reconcile effects and usage.
Help behavior and SDK interrupts are unchanged. See the
[output contract](docs/agent-contract.md#cli-task-output) and
[offline A/B](reports/task-output-ab.json).

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
Task registration preserves dynamic provider identity and its bound client/lock/state,
while deep-copying static choices. Providers are called afresh when a step needs their
domain; results are not cached.

Callbacks must declare synchronous behavior; known coroutine, async-generator and
generator callbacks are rejected without invoking their bodies. Synchronous generator
`Workflow.candidates` and explicit blocking wrappers remain supported. Callback-kind
detection follows only partial `.func` chains, without `inspect.unwrap`. Choice providers
must bind two or three positional arguments; optional keyword-only arguments are allowed,
and three wins when both bind. See the [callback contract](docs/agent-contract.md#synchronous-callback-contract)
and [offline A/B](reports/callback-contract-ab.json). These checks cannot prove ordinary
wrapper return types, prevent trusted import effects or turn the runtime into an async
engine or sandbox. The A/B uses scripted decisions with zero real model, network or UI
calls; it establishes no general success, speed or cost benefit.

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
private journals. Loop shared context retains its inclusive 15,000 JSON-character limit,
measured with `json.dumps(..., ensure_ascii=False)` and default separators. Overflow
normally returns `needs_review/context_budget_exceeded` with count-only `context_budget`
stage/limit/observed metadata, without truncation. Returned decision-call telemetry adds
`context_characters` and `context_character_limit` alongside UTF-8 `context_bytes`.
These units differ; candidate texts, selection questions, full prompts and token/cost
budgets are outside this cap. Direct `Engine.decide` keeps its existing upstream limits.
Prior calls or effects may already exist. See the [budget contract](docs/agent-contract.md#loop-context-budget)
and [offline A/B](reports/context-budget-ab.json) for scope and negative results.

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
