---
name: jev-harness
description: Use a Jev-native agent loop for bounded multi-step tasks when an AI can define trusted tools, meaningful parameter candidates and independent success checks. Generate a task script, run it once and handle terminal evidence; keep exact/fixed work in code and open reasoning in the primary model.
---

# Jev Harness

Contract version: 0.1.10. Install the repository at `@v0.1.10` for a reproducible release;
use `@main` for active development.

Read `jev-harness spec` first. This is a task-script runtime, not a tool interception hook
or a replacement for the primary AI. Prefer it when repeated next-tool/parameter decisions
are semantic and the available action domain and success condition can be bounded.

1. Define the goal, scope, observable success, admitted facts and conversation.
2. `jev-harness init-task task.py` creates a runnable offline scaffold.
3. Register explicit keyword-callable tools with Task.tool; use Parameter descriptions,
   static/dynamic choices and depends_on for related arguments. Use Option to separate
   safe descriptions from private values. Never ask Jev to invent an ID or command.
4. Keep observe/candidate callbacks read-only. Admit safe results via result_context.
5. Test synthetic callback behavior. `check-task` performs static checks only, no execution.
6. Tell the user what goal, observation and tool/parameter candidates Jev will receive.
7. Submit one `jev-harness run ...` call. Inference is billable; use caller-approved credentials.
8. Parse terminal JSON even on exit 2. Only independently verified done means completion.

When any command parser reports an error, expect only the fixed failed/phase arguments/
code invalid_command_arguments packet, script_loaded=false and model_calls=0, exit 2.
Direct CLI main prints that packet and returns 2. Detailed diagnostics, argv values,
usage and error_type are omitted; use spec/help to repair the command before a new run,
not as a tool failure. Suppression is not process-memory zeroization: argparse may create
raw messages temporarily. Normal string argv is supported, arbitrary Python objects are not.
Valid help keeps human text/SystemExit(0), displays prog and can precede unknown-argument
checks; valid long-option abbreviation is unchanged. After parsing, JSON/semantic errors
remain configuration failures. See the contract and reports/cli-arguments-ab.json for
offline parser checks with no real model/network/UI calls or task-success claim.

`check-task` reads UTF-8, parses and compiles without executing the checked script, loading
its module, importing its dependencies or invoking callbacks. Declare an explicit top-level
workflow assignment; a valued annotated assignment counts, an annotation alone does not.
Dynamic/conditional exports are not inferred. A passing syntax_and_export_ok proves only
compilability and the assignment declaration, not workflow type, imports, execution
reachability, tool signatures, candidate providers or effects. It does not guarantee another
Python version or warning policy. invalid_python includes a line; source_not_utf8 identifies
decoding failure. source_warnings contains only python_source_warning codes and line numbers,
without warning/source text in output or stderr. See the contract's Static task checking
section and reports/static-check-ab.json for fixed offline samples with no checked-script
execution, model calls or real UI.

`run` validates configuration before creating/registering/loading the task module: parse
inputs/context/messages JSON, use a nonempty goal, positive integer max_steps, positive
finite timeout, dict inputs/context, user/assistant message list with string content, valid
required_context paths and finite JSON data. CLI JSON must have object inputs/context and
list messages; explicit null is rejected. Only omitted/None Python API fields supply
defaults; wrong false-valued types are rejected. Goal and these fields must serialize as
finite JSON and encode as UTF-8; isolated surrogates are rejected.
Required-path iterables are normalized once; valid paths
missing facts remain runtime needs_context. Invalid CLI configuration returns
failed/phase configuration/code invalid_run_configuration, script_loaded=false,
model_calls=0 and error_type, without raw values or exception text. Valid configuration
still imports trusted Python and can have top-level effects. Preflight is not a sandbox
or a workflow/dependency/archive/credential/business check, and cannot guarantee no later
effects or success. See the contract and reports/run-preflight-ab.json; its synthetic
offline import-marker checks use model-free workflows and no actual API or UI.

CLI run discards writes to redirected Python stdout/stderr during trusted module
creation/import and loop execution, without retaining content. Read spec for optional
task_output metadata: policy=discard, scope=python_streams, stdout/stderr characters
(Unicode code points, no encoding) and binary_bytes (.buffer bytes). Counts cannot recover
discarded debug text or prove success. Return tool results; do not use print as evidence.
SDK Engine.run is unchanged; this output policy applies only to run. Redirects are process-global: do not
overlap CLI tasks in one process; old stream-bound logging handlers, OS descriptors and
subprocesses can bypass them, and concurrent thread output is not isolated. There is no
sandbox, all-output privacy or unconditional terminal-JSON guarantee. Task-path interrupts
restore streams and become quiet nonzero CLI exits without a packet or output counts:
KeyboardInterrupt uses 130; SystemExit preserves exact int 1..255, otherwise uses 1.
Direct CLI main calls raise the normalized SystemExit with original context suppressed;
valid help exits and SDK/Engine interrupts are unchanged. Reconcile effects/usage if no
packet is returned. Ordinary errors retain typed status, and execution_uncertain is not retried.
See the contract's CLI task output section and reports/task-output-ab.json for offline
synthetic output/parsing checks with no real model/network/UI calls.

Register synchronous callbacks. Known coroutine/async-generator/generator declarations,
including partials and callable objects, are rejected without invoking bodies; synchronous
generator Workflow.candidates is allowed. Kind detection follows only partial .func
chains, without inspect.unwrap/__wrapped__, preserving explicit synchronous blocking
wrappers; ordinary wrapper return types cannot be statically proved. Task registration
preserves dynamic provider identity and bound client/lock/state, deep-copies static
choices, and calls the provider afresh when a step needs its domain, without result caching.
Choice providers must bind (ctx, observation) or (ctx, observation, bound_arguments);
optional keyword-only
arguments are allowed. Three arguments win if both forms bind, including variadic/default
signatures. Inspect fixed contract_error codes/roles/kinds rather than callable names or
raw errors. Errors inside executing tools remain execution_uncertain; do not retry them.
This is not an async engine or sandbox, and registration during trusted import does not
prevent earlier top-level effects. check-task stays static; authorization/verification
are unchanged. See the contract and reports/callback-contract-ab.json for offline synthetic
admission/binding with scripted decisions and zero real model/network/UI calls, without
general success, speed or cost claims.

Describe each tool's preconditions and expected effect, and put task priority, order and
exit criteria in the caller's goal and contracts. A next-step tool may gather evidence or
satisfy a prerequisite without completing the entire goal. Candidate position is not
priority; keep business rules in the task instead of the core. The host marks loop
context with decision_stage=tool_selection or parameter_selection. Direct Engine.decide
filtering without that loop marker keeps general candidate-selection semantics. Parameter
binding remains conditional on the selected tool; authorization, independent verification
and exit checks are unchanged.

Admitted non-None tool summaries can advance the next decision when the observation is
unchanged; unadmitted raw results cannot. In one run, the same observation, action ID and
actual bound parameters execute at most once. A repeat stops before execution with
`blocked/repeated_action_state`; history growth is not permission to repeat an effect.
Polling an identical call against a fixed observation is unsupported. Handle it inside
a trusted tool with bounded attempts/time, or expose meaningful observed progress.

When using `verify_state`, supply nonempty text or at least one control condition.
Each expected control field must be observed; a missing field is not observed `null`.
Admitted results and model exit choices never replace independent completion verification.

Read spec.context_admission: the loop's existing inclusive limit is 15000 serialized
JSON characters, from json.dumps(..., ensure_ascii=False) with default separators, not
UTF-8 bytes or tokens. A context_budget_exceeded terminal may include count-only
context_budget (scope, stage, unit, limit, observed); inspect context_projection,
tool_selection or parameter_selection before revising the caller's admitted projection.
Returned call telemetry adds context_characters/context_character_limit alongside
context_bytes; exception paths can lack these measurements. Candidate texts, selection
questions/full prompts and token/cost budgets are excluded. Direct Engine.decide retains
separate upstream limits. No automatic truncation or caching is added; prior calls/effects,
unknown usage and uncertain execution still require reconciliation. See the contract,
context page and reports/context-budget-ab.json for offline synthetic measurement with
zero real model/network/UI calls, added terminal bytes and no quality/speed/fee claim.

Do not retry ambiguous external execution. Caller tools own identity, authorization,
idempotency, business transactions and reconciliation. Scripts are trusted Python, not a
sandbox. Protect private journals; recover only necessary evidence for unresolved items.

An unresolved selection may include a host-generated diagnostic with stage
tool_selection or parameter_selection, registered tool_id/parameter for the latter,
allowlisted reason_codes, and automatic_retry=false. Each selection-call entry in
telemetry.calls carries its stage and applicable identifiers. Static domain, policy and
execution errors retain existing terminal reasons. Diagnostics contain no exception
text, response body or bound values, and do not alter status, eligibility or authorization.
Use credential codes to fix host configuration; use uncertainty/selection codes to
review admitted context or candidate meaning. Inspect prior effects before a new run;
unknown errors fall back to generic codes, not an upstream root-cause claim.
The harness does not repeat task calls automatically. The pinned SDK's bounded
429/503/529 retries remain; automatic_retry=false does not promise one network request.
See the contract's Decision diagnostics section for the whitelist. Synthetic offline
HTTP-mock acceptance has zero real model calls, increases terminal bytes, and does not
establish real semantic recovery success.

Read spec.request_planning for an empty native plan: telemetry.planning or
telemetry.calls[].planning has scope=current_selection, phase=request_planning,
inference_dispatched=false and fixed reasons request_needs_narrowing/request_needs_context/
request_planning_review. Known typed statuses remain distinct; unknown statuses become
UNAVAILABLE with the generic code, never a guessed cause. Empty record lists have no
reason codes; other selection paths omit planning. The loop diagnostic keeps tool/parameter
stage. Use it to repair candidates/descriptions or required context/record fields while
preserving goal and safety constraints; do not blindly retry. Known-zero usage is only for
that selection: prior calls/effects or unknown usage remain. No fit rules, caps, prompts or
model choices change. Generic full-spec ValueError and dispatched HTTP413 are not
reclassified (HTTP413 keeps its safe code and unknown usage). See the planning contract
and reports/planning-diagnostics-ab.json for offline synthetic checks with no real
model/network/UI calls or accuracy/speed/fee claim.

Use generic browser/desktop adapters only within their platform and target scope. Headless
Camofox must preserve the named session; native desktop needs an unlocked target app.
No declared adapter means no claim of application coverage. Exact selectors/IDs/computation
and fixed sequences need no inference; open-ended generation remains with the primary AI.

See https://apixly-ai.github.io/jev-harness/agent-contract.html and its context/adapters
pages for complete contracts. Tool and parameter domains are recomputed; no result caching.
