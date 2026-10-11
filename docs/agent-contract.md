# The AI-native task contract

[简体中文](agent-contract.zh-CN.md)

The product is a reusable task runtime, not a library of application-specific cases.
An agent should learn one interface and supply its business tools as a short script.

Distribution: **apixly-jev-harness**. Python: `apixly_jev_harness`. CLI aliases:
`apixly-jev-harness` and `jev-harness`. Install from the exact repository URL below;
the existing PyPI jev-harness package is a different project.

## Install and run your first task

Python 3.10+ and Git are required. Installation is offline with respect to model calls;
package downloads still require network access. Pin v0.1.15 for a reproducible release;
use `@main` instead for active development.

```sh
python -m venv .venv
. .venv/bin/activate
pip install 'git+https://github.com/apixly-ai/jev-harness.git@v0.1.15'
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

## CLI argument parsing

When argparse reports an error in any command parser, the CLI prints only this fixed
packet and exits 2; a direct `main` call prints it and returns 2:

```json
{
  "status": "failed",
  "complete": false,
  "phase": "arguments",
  "code": "invalid_command_arguments",
  "script_loaded": false,
  "model_calls": 0
}
```

This happens before command dispatch or task-module loading, and exports no raw error
message, argument values, usage or `error_type`. Detailed parser diagnostics are lost.
Argparse may temporarily construct a message containing argv values; suppressing its
output does not zeroize argv or transient strings in process memory. This contract supports
normal CLI string arguments, not arbitrary Python objects passed as argv.

Valid `--help` retains human text, `SystemExit(0)` and original parser precedence. Help
may exit before a later unknown-argument check, so not every invocation containing an
unknown token produces an error packet. Help displays the program name (`prog`); it is
not covered by raw-message suppression. Valid long-option abbreviation remains unchanged.

Inspect `spec`/help and repair the command for an `arguments` failure; it is not a tool
execution failure. Once parsing succeeds, malformed JSON or invalid `run` configuration
still uses phase `configuration` and code `invalid_run_configuration`. Runtime task
statuses follow after trusted loading; quiet task interruptions still have no packet and
require effect/usage reconciliation. The SDK/`Engine.run` is unchanged. The
[cli-arguments A/B](../reports/cli-arguments-ab.json) is offline synthetic parser checking,
with no real model, network or UI calls; it does not establish task success.

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
`Engine.run` is unchanged. This output policy applies only to `run`; argument-error
packets apply to all command parsers. Configuration preflight, valid help and successful
`spec`, `skill`, `check-task` and `init-task` keep their existing contracts.

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
nor absence of effects; reconcile before a new run. Valid help exits remain unchanged,
and the SDK/`Engine.run` retains its original interrupt behavior. The
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

Choice providers must bind two or three positional arguments, rather than have a
particular total parameter count. Optional keyword-only arguments are allowed. Binding
starts with `inspect.signature(provider, follow_wrapped=False)`, which still respects
an explicit `__signature__`:

- An entry without `*args`, or with at least three explicit positional slots, uses that
  entry signature. A synchronous bridge can receive bound parents even when its
  `__wrapped__` delegate advertises only two arguments; the reverse two-slot entry stays two.
- A `*args` entry with fewer than three explicit positional slots retains the default
  advertised delegate signature for compatibility. The selected arity must bind both
  the advertised contract and entry signature.

Try three arguments first, then two. An entry requiring four arguments, or required
keyword-only arguments that prevent either form from binding, reports
`CallbackContractError` with code `provider_signature_unsupported` and callback `choices`
before invoking the provider body. Partial and callable-object providers follow these rules.
This changes provider arity only; `Task.tool` signature checks and callback-kind detection
are unchanged. No `__wrapped__` unwrapping is added to kind detection, no provider body is
invoked during admission, and this remains a synchronous engine.
Explicit signature metadata can still be wrong, and complex one/two-slot `*args` wrappers
with misleading delegate metadata can remain unsupported. Use an explicit two/three-argument
entry or accurate `__signature__`; neither introspection nor admission proves body behavior.
See the [provider-signature A/B](../reports/provider-signature-ab.json) for the test scope.

Task registration preserves a dynamic provider callable's identity, including its bound
client, lock and state, while deep-copying static choices. Whenever a step needs the
provider's domain, it invokes the provider afresh; no provider result is cached.

For each domain acquisition, `_domain` checks duplicate IDs and its existing size limit,
then deep-copies the complete option list before handing it to selection. This isolates
ordinary `Option` values and raw dictionary/list values from later mutations to the
provider's shared source while the choice waits. The actual bound value comes from this
domain snapshot rather than a source reference changed during selection. Both default
staged binding and joint catalogs retain their interfaces; the snapshot is per acquired
domain, not a promise to reuse one menu across every later binding step.

Providers retain identity and are called again whenever a domain is needed. No result
cache, atomic provider acquisition, global freshness guard or sandbox is added. Deepcopy
adds time and memory overhead based on the object structure of all candidate values,
including unselected ones. Immutable strings may be retained; serialized JSON bytes
do not measure new heap allocation. A custom deepcopy can fail or execute trusted
Python behavior; its behavior is not proven. An unselected failure can therefore move
an earlier-successful flow to an earlier failed
or blocked result. Existing failure/unknown-usage handling and execution permissions
remain. Caller tools still own business freshness and identity. See the
[parameter-snapshot A/B](../reports/parameter-snapshots-ab.json); no speed or fee guarantee
follows from copying.

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

### Loop context budget

The existing loop shared-context limit is 15,000 serialized JSON characters, inclusive.
It measures `len(json.dumps(context, ensure_ascii=False))` with default separators,
including JSON syntax and escapes, rather than raw text, UTF-8 bytes or tokens. Projection
is checked first; tool/parameter selection then checks the added stage and binding context.
Candidate-record texts, selection questions, the full prompt and cost budgets are excluded.

A terminal with reason `context_budget_exceeded` may include host-generated count-only
`context_budget` metadata, for example:

```json
{
  "reason": "context_budget_exceeded",
  "context_budget": {
    "scope": "loop_shared_context",
    "stage": "parameter_selection",
    "unit": "json_characters",
    "limit": 15000,
    "observed": 15001
  }
}
```

The observed count is illustrative. Stages are `context_projection`, `tool_selection`
or `parameter_selection`; no raw context is exported in this metadata. Returned decision
call entries add `context_characters` and `context_character_limit` alongside existing
UTF-8 `context_bytes`; an exception path need not supply these measurements. Overflow
normally stops the affected inference before calling Jev with `needs_review`, without
automatic truncation or caching. Earlier calls/effects and existing uncertainty handling
remain; inspect telemetry and reconcile effects before a new run.

Direct `Engine.decide` does not use this loop cap; existing upstream full-spec and provider
limits still apply. See [context management](context.md) and the
[offline context-budget A/B](../reports/context-budget-ab.json). The A/B covers synthetic
admission/measurement with no real model, network or UI calls. Additional metadata costs
terminal bytes; it does not prove semantic quality, speed or fee savings.

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

The helper matches control values recursively using exact builtin `None`, `bool`, `int`,
finite `float`, `str`, `list`, `tuple` and `dict` types. `True`/`1` and `False`/`0` differ,
including nested values and dictionary keys; numeric `1`/`1.0` equivalence remains,
including numeric keys. Lists/tuples compare elements recursively within the same kind,
without list/tuple coercion. Dictionary keys are matched by typed null/boolean/number/string
categories. Unsupported values, keys and subclasses do not match. Value comparison does
not delegate completion to a custom object's `__eq__`.

The helper's observed root must be an exact builtin dictionary with builtin-string field
keys before looking up text/controls; unsupported roots do not match. For control checks,
expected records must be exact builtin dictionaries with builtin-string field
keys and a builtin-string label; invalid records retain the existing
`control_check_requires_label_and_expected_fields` configuration error. For control checks,
observed controls must be builtin list/tuple with exact dict records and builtin-string
field keys. A malformed record makes the helper return false rather than being filtered
out to manufacture a unique match. This outer-field rule does not prohibit supported
numeric keys inside nested values. Comparison avoids custom equality; helper construction
and the surrounding trusted loop can still invoke Python hooks through deepcopy or JSON
sorting, so it is not a sandbox or a claim of no arbitrary Python execution.

Expected text accepts only `None` or builtin `str`; other types/subclasses raise the
existing `verification_text_required` configuration error before any text `strip` call.
This construction rejection differs from unsupported comparison values returning false.
When checking text, the observed value must be builtin `str`; a list/dictionary containing
the expected text does not satisfy the condition. Earlier implicit custom-matcher/subclass
support is narrowed: use caller-owned `verify` for deliberately different semantics or
complex objects. This changes `verify_state` only, not global input admission, custom
verifiers, model choice, authorization or candidate refresh/no caching. A failed initial
check can now permit subsequent tool execution and more selection calls instead of a
false `done`; normal execution gates still apply. The
[verification-types A/B](../reports/verification-types-ab.json) concerns independent typed
verification, not AI semantic accuracy or real browser/desktop acceptance. No whole-matrix
behavior parity, speed or fee benefit is implied.

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

If `DecisionStop` occurs in the current execution window, `execution_uncertain` includes
the current pending bound `action_id` when present. This window covers execute, result
admission, immediate observation and unchanged-state verification. The ID is not inferred
from history; stops before execution or after clearing pending do not acquire an old ID.
Ordinary exceptions already carry the available pending ID. Use it to locate private
journal evidence and reconcile the target. It proves neither effect success nor execution
count, is not an idempotency key and does not authorize rerunning. No bound arguments are
added to this terminal field. Exit behavior, authorization, retry policy and usage handling
are unchanged; unknown usage remains unknown. See the
[execution-identity A/B](../reports/execution-identity-ab.json) for this interface boundary.

## Decision diagnostics

A terminal packet may include an optional host-generated `diagnostic` for an unresolved
tool or parameter selection call. It does not change the terminal status, execution
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
`tool_id` and `parameter` from the registered binding context. Each selection-call
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
- Request planning: `request_needs_narrowing`, `request_needs_context`,
  `request_planning_review`.

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

## Request planning handoff

When the pinned native choice planner produces no inference items, the returned telemetry
includes `planning`; in a loop this appears in `telemetry.calls[].planning`, and a direct
choice uses `telemetry.planning`. For example:

```json
{
  "planning": {
    "scope": "current_selection",
    "phase": "request_planning",
    "inference_dispatched": false,
    "reason_codes": ["request_needs_narrowing"]
  }
}
```

Typed planning judgment `NEEDS_NARROWING` maps to `request_needs_narrowing`; `NEEDS_CONTEXT`
maps to `request_needs_context`. Unknown planning judgments become `UNAVAILABLE` with the
generic `request_planning_review`, without exporting raw status text or inventing a cause.
An empty record list has empty reason codes and retains its existing result semantics.
Other selection paths omit this metadata. Loop diagnostics preserve these allowlisted
codes with the existing tool/parameter stage; runtime exit states are unchanged.

`inference_dispatched: false` proves only that this selection did not enter the native
inference runner. Its existing known-zero usage remains; it does not establish zero
requests, effects or complete usage for the whole loop. Earlier spent calls, effects and
unknown usage remain in the terminal evidence. Use the stage to inspect program-supplied
candidates/descriptions or required context/record fields, keeping the goal and safety
constraints. Repair the input deliberately rather than blindly retrying.

This adds no admission caps or changed fit rules, prompts or model choices. It is distinct
from `model_review`, provider failures and generic validation exceptions. The separate
16,000-character full-spec `ValueError` path is not reclassified; a dispatched HTTP413
retains `http_413_body_suppressed` and unknown usage. The loop's inclusive 15,000 JSON-character
cap, authorization, verification and uncertainty handling are unchanged. The
[planning-diagnostics A/B](../reports/planning-diagnostics-ab.json) uses offline synthetic
planning/dispatch checks with no real model, network or UI calls, and does not establish
semantic accuracy, speed or fee savings.

## Transport counters owned by the run

`telemetry.requests` retains its existing meaning: the sum of decision telemetry, with
native Choice reporting logical packed requests. Existing per-call `transport` evidence
is retained. Optional `telemetry.owned_transport` separately records this run's owned
provider-client counters from Session start to terminal finish, for example:

```json
{
  "owned_transport": {
    "scope": "run_owned_provider_client",
    "snapshot": "terminal_finish",
    "request_attempts": 3,
    "clients_created": 1,
    "client_reuses": 2,
    "counters_complete": true
  }
}
```

The counts illustrate the metadata shape, not A/B measurements. They are differences of the
owned `Client.stats` fields `requests`, `clients_created` and `client_reuses`. One logical
request can have three SDK attempts after retries, while credential rejection can leave
one logical request and zero attempts. Snapshotting occurs before the journal's terminal
write and client close; the returned packet and journal use the same snapshot.
`spec.transport_counters.snapshot` is the exact runtime value `terminal_finish`;
`snapshot_timing` separately describes ordering. This machine contract is not a JSON Schema validator.

Each counter requires exact nonnegative integers at the start and finish, with a finish
value no lower than the start or a witnessed Session.run counter. Missing, unreadable,
boolean, negative, string or decreasing counters become `null`, not an inferred zero.
This checks the observed bounds, not every reset between observations.
`counters_complete` means all three counter deltas are available; it does not establish
complete token usage. With no active owned Session, the metadata is omitted. Absence is
unknown rather than evidence of zero attempts.

These are SDK attempt counters, including its existing retries, not proof that HTTP was
sent, a server received it, inference occurred or billing is complete. An attempt can be
counted before JSON encoding fails, without entering the HTTP transport. Client counts
refer to HTTP client objects/reuse, not TCP connections; other tool traffic and provider
clients are outside this scope. Model identity, unknown usage, authorization, execution,
exit states and retry policy are unchanged. See the
[transport-counters A/B](../reports/transport-counters-ab.json) for the test scope;
no price, cost-saving or speed guarantee follows from these counters.
