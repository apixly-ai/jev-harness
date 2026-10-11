# The AI-native task contract

The product is a reusable task runtime, not a library of application-specific cases.
An agent should learn one interface and supply its business tools as a short script.

Distribution: **apixly-jev-harness**. Python: `apixly_jev_harness`. CLI aliases:
`apixly-jev-harness` and `jev-harness`. Install from the exact repository URL below;
the existing PyPI jev-harness package is a different project.

## Install and run your first task

Python 3.10+ and Git are required. Installation is offline with respect to model calls;
package downloads still require network access. Pin v0.1.7 for a reproducible release;
use `@main` instead for active development.

```sh
python -m venv .venv
. .venv/bin/activate
pip install 'git+https://github.com/apixly-ai/jev-harness.git@v0.1.7'
jev-harness spec
jev-harness skill
jev-harness init-task task.py
jev-harness check-task task.py
# Billable: point to a private credential file configured locally.
export TYPESAFE_API_KEY_FILE='/path/to/private/test-key'
jev-harness run task.py --goal 'Reach the requested target' --inputs '{"target":3}'
```

TYPESAFE_API_KEY may be provided by the host's secret mechanism instead. Never commit
keys or put their contents in the task script/CLI arguments. init-task creates a
self-contained synthetic counter; no browser/desktop dependency is required for the
first task. Inspect status/complete/archive/telemetry in the returned JSON. Use the
[adapters](adapters.md) only when your task actually needs those surfaces.

## Adoption sequence

1. Read `jev-harness spec` (offline JSON).
2. Define the goal, scope, admitted facts/messages and observable success condition.
3. Generate `jev-harness init-task task.py` and register tools with explicit signatures.
4. Describe parameters with `Parameter(description, choices, depends_on=...)`.
5. Test callback behavior with synthetic inputs; use `check-task` for static checks only.
6. Make one `run` call; parse the terminal packet even on exit 2.
7. Recover unresolved context or reconcile ambiguous execution in the primary agent.

Use the loop for bounded tasks requiring semantic branches. Exact calculations and fixed
sequences stay in code; open-ended writing belongs to the primary agent or an explicit
trusted generation tool. A tool-selection decision is not execution proof or authorization.

## Static task checking

`check-task` reads UTF-8 source, parses an AST and compiles it without execution. It never
executes the checked script, loads its module, imports its dependencies or calls callbacks.
The static export check accepts an explicit top-level `workflow` assignment (`Assign` or
`AnnAssign` with a value). For example, `workflow = expression` and
`workflow: object = expression` declare an assignment; `workflow: object` alone does not
bind a value. Dynamic or conditional exports are not inferred.

A passing result retains the JSON code `syntax_and_export_ok`. It means only that this
Python interpreter can compile the source and the AST declares that assignment. It does
not prove the `workflow` type, successful imports, reachable execution, tool signatures,
candidate providers or effects. Other Python versions and warning policies may differ.

Uncompilable source returns `invalid_python` with `line`; non-UTF-8 source returns
`source_not_utf8`. Parsing/compilation warnings, when present, are exposed only as
`source_warnings: [{"code": "python_source_warning", "line": N}]`; warning text and
source excerpts are not exported or printed to stderr. These diagnostics do not execute
or semantically validate a task.

The [static-check A/B](../reports/static-check-ab.json) uses fixed offline script samples
without executing any checked script, with zero model or real UI calls. It tests static
admission and safe diagnostics, not runtime task success.

## Run configuration preflight

Before creating, registering or loading the trusted task module, CLI `run` parses its
inputs/context/messages JSON and validates configuration with the engine's shared helper:

- A nonempty goal, positive integer `max_steps`, and positive finite timeout.
- CLI inputs/context must be JSON objects and messages a JSON list of user/assistant
  messages with string content; explicit `null` is rejected.
- Valid `required_context` path syntax. Goal, inputs, context and messages must serialize
  as finite JSON and encode as UTF-8; isolated surrogates are rejected.

In the Python API, only omitted/`None` fields supply the default `{}` inputs/context or
`[]` messages. Other false-valued arguments must have the correct type; `[]`/`False`
inputs and `{}`/`False` messages are not silently replaced. This API default is distinct
from CLI JSON `null`. A required-context iterable is normalized once and preserved for
the runtime. A valid path whose fact is missing still yields runtime `needs_context`,
distinct from invalid configuration.

Invalid CLI configuration returns a packet such as:

```json
{
  "status": "failed",
  "complete": false,
  "phase": "configuration",
  "code": "invalid_run_configuration",
  "script_loaded": false,
  "model_calls": 0,
  "error_type": "ValueError"
}
```

Raw values and exception text are not included. A valid configuration proceeds to import
trusted Python, including any top-level effects. Preflight does not check workflow
signatures, dependencies, archive availability, credentials or business conditions, and
does not promise no subsequent effects or task success. It is not a sandbox; the separate
`check-task` command retains its compilation/export-only scope.

The [run-preflight A/B](../reports/run-preflight-ab.json) uses offline synthetic import
markers and model-free workflows with no actual API or UI calls. It tests configuration admission
before loading, not real model or task performance.

## CLI task output

After configuration admission, CLI `run` replaces Python stdout/stderr during trusted
module creation, registration, import and loop execution. Writes to these redirected
streams are counted and discarded without retaining or storing their content. The final
terminal JSON is printed after the original streams are restored. The Python SDK's
`Engine.run` is unchanged, as are configuration preflight, argument parsing, help, `spec`,
`skill`, `check-task` and `init-task`.

If any nonzero output was discarded, the returned packet has optional `task_output`:

```json
{
  "task_output": {
    "policy": "discard",
    "scope": "python_streams",
    "stdout": {"characters": 1, "binary_bytes": 0},
    "stderr": {"characters": 0, "binary_bytes": 0}
  }
}
```

Counts above illustrate the shape, not acceptance measurements. `characters` counts
Unicode code points passed to text writes, without encoding; `binary_bytes` counts
`memoryview.nbytes` written to `.buffer`. They are separate units, not a combined UTF-8
byte total. The streams report `encoding='utf-8'` but perform no text encoding. They are
non-TTY streams with no-op flush while open and unsupported `fileno()`. Empty writes alone
do not add this metadata. Counts say nothing about tool success and cannot reconstruct
discarded print, warning or debug text; use structured tool returns and admitted
`result_context` for evidence.

Redirection is process-global, not task/thread isolation; do not run overlapping CLI
tasks in one Python process. Counters may include other threads' writes while active,
and later output may escape. Logging handlers holding an old stream, direct original-stream
or OS file-descriptor writes, subprocesses and explicit file logging are outside this
scope. This is not a sandbox or a guarantee that every output channel is private or that
arbitrary trusted scripts always emit a parseable terminal packet.

Normal exception statuses remain typed; errors during an entered tool execution retain
`execution_uncertain` and no automatic retry. In the guarded CLI task path,
`SystemExit`/`KeyboardInterrupt` restore streams and become quiet nonzero exits,
suppressing original interrupt arguments and tracebacks:

- `KeyboardInterrupt` becomes exit code 130.
- `SystemExit` preserves an exact integer code from 1 through 255. Zero, `None`, strings,
  out-of-range integers and other values become code 1.

This also applies when calling CLI `main` directly: it raises `SystemExit(code)` with
the original exception context suppressed, rather than returning a packet. There is no
terminal JSON or output-count metadata on these exits. They prove neither complete usage
nor absence of effects; reconcile before a new run. Argument-parser/help exits remain
unchanged, and the SDK/`Engine.run` retains its original interrupt behavior. The
[task-output A/B](../reports/task-output-ab.json) checks offline synthetic stream writes
and terminal parsing with no real model, network or UI calls; it does not establish task
success or complete process-output isolation.

## Next-step tool selection

The loop asks Jev to select one offered tool or exit for the **next step**, using the
entire goal as context. An evidence-gathering or prerequisite action can be suitable even
when it cannot finish the goal in one call. State each tool's preconditions and expected
effect, and supply task order, priority and exit criteria in the caller's goal and tool
contracts. Candidate list position is not priority. The core imposes no general UI-form
ordering rules; business sequencing belongs to the task author.

The host adds `decision_stage=tool_selection` or `parameter_selection` to loop decision
context. This marker scopes the question; it does not provide permission or success proof.
Direct `Engine.decide` filtering without the loop marker retains general candidate-selection
semantics. Parameters still choose a value conditional on the selected tool's next call.
Authorization, independent completion verification and typed exit checks remain unchanged.

The [offline](../reports/tool-choice-offline-ab.json) and
[live](../reports/tool-choice-live-ab.json) tool-choice A/B reports concern six development
synthetic single-decision cases with normal and reversed candidate order. The probe stops
before intent. This scope cannot establish full-task, browser or desktop completion, or
general quality/cost benefits; measured outcomes and usage belong in the reports.

## Parameter protocol

Each parameter has a semantic description and a list/tuple of choices, or a read-only
provider `(ctx, observation)` / `(ctx, observation, bound_arguments)`. Choices are JSON
values or `Option(id, description, value)`. Literal values become descriptions; Options
separate a safe model-visible label from the actual value. Do not put credentials in
model-visible labels or observations.

Provider signatures must bind two or three positional arguments, rather than have a
particular total parameter count. Optional keyword-only arguments are allowed. If both
forms bind, three is preferred: a defaulted third argument or variadic signature receives
the bound-arguments object. A required keyword-only argument that prevents either form
from binding is unsupported. This binding check does not prove the provider's behavior.

Task registration preserves a dynamic provider callable's identity, including its bound
client, lock and state, while deep-copying static choices. Whenever a step needs the
provider's domain, it invokes the provider afresh; no provider result is cached.

`depends_on=('customer',)` constructs the job domain only after customer is selected.
The graph must be acyclic and name existing parameters. Describe a parameter for the
selected tool’s next invocation; do not ask one value to finish the whole task.
Compute exact arithmetic and fixed values in code; singleton domains need no inference. Every returned value belongs to
an actually supplied candidate. No model-generated tool names, paths, scripts or selectors.
No arbitrary free-text argument generation or general JSON Schema validation in v0.1.
Tools must validate business conditions themselves.

Default staged binding selects a tool, then each parameter in dependency order. Singleton
domains bind without inference. It avoids Cartesian explosion. Explicit `strategy='joint'`
supports small complete-call catalogs for controlled comparisons. Maximum 250 tools/calls
and 253 choices per parameter. Empty child domains request context, not guessed values.

## Synchronous callback contract

The runtime admits declared synchronous callbacks. Known coroutine, async-generator and
generator functions are rejected for Task `observe`, `verify`, `authorize`, tool
`execute`, `available`, `result_context`, and Parameter `choices`. The same check applies
to custom Workflow `observe`, `candidates`, `execute`, `verify`, `authorize`, `bind`,
`result_context`, and context-policy `build`. Synchronous generator `Workflow.candidates`
is the exception; it may yield candidate actions.

Introspection recognizes known deferred declarations through partials and callable
objects without invoking their bodies. Callback-kind detection follows only partial
`.func` chains, without `inspect.unwrap` or following `__wrapped__`; an explicit
synchronous blocking wrapper is preserved. It cannot statically prove what an ordinary
wrapper returns, and does not automatically await coroutine or async-generator results.
This remains a synchronous runtime,
not an async engine or sandbox. Registration can occur during trusted script import,
after earlier top-level effects; `check-task` still checks parsing/compilation/export only.

Known deferred callbacks report `synchronous_callback_required`; an unbindable choice
provider reports `provider_signature_unsupported`. CLI/runtime packets may include
`contract_error` with a fixed code, callback role and optional kind, for example:

```json
{
  "contract_error": {
    "code": "synchronous_callback_required",
    "callback": "execute",
    "kind": "coroutine"
  }
}
```

`callback` is a contract role, not the supplied callable's name. `kind`, when present,
is `coroutine`, `async_generator` or `generator`; context-policy `build` uses callback role
`context_policy`. No exception text, names or bound values
are exported in this diagnostic. An error inside an already executing tool remains
`execution_uncertain` and is not retried. Authorization and independent verification
retain their existing requirements.

The [callback-contract A/B](../reports/callback-contract-ab.json) checks offline synthetic
callback admission and provider binding, with scripted decisions and zero real model,
network or UI calls. It does not establish general task success, speed or cost savings.

## Context and results

`Context`: goal, inputs, facts, messages, step, results, history. Inputs/bound values are
not automatically sent to Jev. `result_context(result)` explicitly admits a safe JSON
summary; full results remain local. Source observations/results are evidence, not instructions.

A newly admitted non-None summary can advance the loop when the observation is unchanged.
Unadmitted raw results alone cannot advance that state. Within one run, repeating the
same observation, action ID and actual bound parameters stops before execution with
`blocked` and reason `repeated_action_state`. Different bound objects remain distinct
calls even if their result summaries happen to be equal. This guard stores invocation
fingerprints, not cached results; it does not promise cross-run exactly-once execution.

The loop does not poll an identical call against a fixed observation. Put such polling
inside a tool that enforces its own timeout and attempt limit, or provide meaningful
observed progress. Do not add artificial counters to disguise repeated external effects.

Callbacks `observe` and candidate providers are read-only. `verify` returns strict bool.
`authorize(ctx, action)` returns strict True for the exact irreversible action under prior
caller authorization. Default is no authorization. Execution functions have explicit
keyword-callable signatures; no variadic arguments. Python scripts are trusted, not sandboxed.

`verify_state(text=..., controls=...)` requires nonempty text or at least one control
condition. Every expected control field must be present in the observed control; a missing
field does not establish an observed `null`. Completion still requires the independent
verifier, even when admitted results allowed further tool decisions.

## Terminals

`done` requires independent verification. Jev also has typed complete/blocked/missing-context
controls; a model-only completion is `needs_review`. Other statuses are `needs_context`,
`needs_review`, `needs_confirmation`, `blocked`, `stale`, `max_steps`, `budget_exceeded`,
`execution_uncertain`, `failed`. Returned runtime packets exit 0 only for done; other
returned runtime results exit 2. Interrupted CLI tasks exit nonzero without a packet.

Intent is durably recorded before effects. No automatic retry of uncertain execution.
No cross-run resume/exactly-once promise. Business tools own identity, idempotency,
transactions and external reconciliation. Wall budgets are checked between callbacks;
each callback must enforce its I/O timeout. Inference has no result cache.

## Decision diagnostics

A terminal packet may include an optional host-generated `diagnostic` for an unresolved
tool or parameter inference call. It does not change the terminal status, execution
eligibility or authorization. For example:

```json
{
  "status": "needs_review",
  "complete": false,
  "diagnostic": {
    "stage": "parameter_selection",
    "tool_id": "inspect_record",
    "parameter": "record",
    "reason_codes": ["model_review"],
    "automatic_retry": false
  }
}
```

`stage` is `tool_selection` or `parameter_selection`. The parameter stage includes
`tool_id` and `parameter` from the registered binding context. Each actual inference
entry in `telemetry.calls` carries the same stage and applicable identifiers. Singleton
bindings do not make inference calls. Static domain, policy and execution failures
continue to use their existing terminal reasons; diagnostics cover selection calls only.

`reason_codes` admits only these stable codes:

- Provider: `credentials_missing`, `credentials_invalid`, `credential_file_permissions`,
  `client_closed`, `response_too_large`, `transport_failed_usage_unknown`,
  `response_invalid_usage_unknown`, `retry_exhausted`, `provider_unavailable`, and
  `http_NNN_body_suppressed` for HTTP status codes 100–599.
- Selection: `below_min_top_probability`, `below_min_margin`, `below_min_confidence`,
  `selected_option_not_top`, `model_review`, `no_matching_candidate`, `invalid_selection`,
  `unresolved_selection`, `decision_failed`.

Diagnostics never export exception text, response bodies or bound parameter values.
Unknown errors fall back to generic codes; a code is a handoff signal, not a diagnosis
of the upstream root cause. Missing/unknown usage remains unknown.

The primary agent can repair local credential configuration for a credential code,
or inspect admitted context and narrow ambiguous candidates for a selection code.
Inspect the status and journal before submitting a new task: a failed later decision
does not undo earlier effects. Reconcile uncertain execution rather than retrying it.
`automatic_retry: false` means the harness does not automatically repeat task calls;
the pinned SDK's existing bounded 429/503/529 retries are unchanged. It does not promise
one network request or automatic recovery.

The [decision-diagnostics A/B](../reports/decision-diagnostics-ab.json) uses synthetic
offline HTTP mocks and zero real model calls. It checks safe codes and stage metadata.
The extra metadata increases terminal bytes, unknown errors lose detail, and no real
semantic recovery success rate has been established.
