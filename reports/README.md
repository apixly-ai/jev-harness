# Acceptance evidence and scope

[简体中文](README.zh-CN.md)

The runtime is the product; these cases test reusable seams rather than special-case
features. All inputs are local synthetic data. No bookings or messages were sent.

Browser acceptance for 0.1.0: real Jev 1.13.0 with Camofox in a named headless session,
four tool executions, independently verified final DOM text and fields. An early sequence
required review; another stopped at a target authorization gate. Those negatives remain
in the published accounting. No universal speed/cost or open-web completion claim.

Desktop acceptance is blocked by a locked Mac. Independent computer-use inspection
confirmed the lock. Accessibility trust alone did not establish an observable target
window. Offline surface tests pass; native macOS/Windows completion remains unverified.

[Machine-readable acceptance](acceptance.json) records run outcomes, whole-operation
elapsed time, known usage and uncertainty. Actual provider usage is grouped by returned
model where available; missing model identity remains unknown. Monetary estimates are
not invoices and no current tariff is assumed.

## AI onboarding and parameter semantics

The generated task template was exercised with real Jev: initial generic parameter
questions returned review; conditional questions then completed in two tool executions
with three model requests. [Paired prompt A/B](parameter-prompt-ab.json) freezes the
small synthetic state and compares generic/conditional questions, three repeats each.
Selected-ID correctness changed from 0/3 to 3/3 in this development fixture; default
uncertainty admission is reported separately. More input context is a recorded negative;
this is not held-out calibration or a broad model-performance claim.

[Offline joint/staged comparison](parameter-ab.json) also retains the extra staged
decisions for small independent domains and joint enumeration's oversized-space stop.

## Evidence progress and completion guards (0.1.1)

The [offline runtime A/B](evidence-progress-ab.json) executes the published 0.1.0 source
at commit `e00bb1c1c6e063030446e7e795d33cc371f21032` and the candidate against seven
fixed synthetic scenarios, three paired repeats each. The baseline meets 9/21 expected
outcomes; the candidate meets 21/21. Expected outcomes include intentional blocking and
configuration rejection, not just completion. The regression cases cover read-only
evidence followed by another tool, equal summaries for different bound objects, repeated
query/effect prevention, unadmitted private results, empty completion conditions and
missing control fields incorrectly interpreted as observed null.

The report records all statuses, whole-operation timing, returned context bytes,
scripted decision/context counts, candidate source hashes and zero actual model usage.
There are no paid calls, native browser/desktop operations or measurements of semantic
accuracy in this experiment. Added continuation doubles the scripted decisions from
15 to 30 over these fixtures and increases context volume; there is no savings claim.
Identical calls against a fixed observation remain unsuitable for repeated polling.

Reproduce from a full Git checkout with `.[dev]` installed (no credential required):

```sh
python benchmarks/progress.py --output local-results/evidence-progress-ab.json
```

The output must be a new file. Timings cover task creation, decisions, callbacks and
private journal writes, excluding interpreter/import and source-snapshot setup. CI runs
both offline benchmarks on Python 3.10, 3.12 and 3.14. The earlier live browser evidence
belongs to 0.1.0 and was not rerun for 0.1.1; desktop acceptance remains unverified.

## Decision diagnostics (0.1.2)

The [offline diagnostic A/B](decision-diagnostics-ab.json) compares the exact published
0.1.1 source at `4f8e274bf598fbe674ee08eccccda1fa55655732` with the candidate. Ten fixed
synthetic scenarios run three paired repeats each through the pinned SDK and typed-batch
seam using HTTP mocks or injected sanitized ProviderError. No credentials, model calls,
browser or desktop operations are needed.

Both arms meet all 30 expected terminal statuses and execution counts, including
intentional abstention/blocking, and preserve unknown usage. Diagnostic protocol checks
change from 3/30 to 30/30: the baseline only meets the successful case's expected absence
of a failure diagnostic; the candidate identifies credentials, safe HTTP status,
uncertainty, explicit model review and no match at the tool or parameter stage. This is
coverage of new metadata, not improved semantic accuracy or demonstrated AI recovery.

Both arms have 36 scripted decisions and 33 mock HTTP attempts. The pinned SDK already
retries 429/503/529 up to three times; those retries are simulated here and unchanged.
Returned terminal bytes increase from 37,111 to 43,251 over this run. All measured times,
context bytes, mocked model identities, unknown usage and statuses remain in the report.
Real model usage is explicitly zero and distinct from synthetic response tokens.
There is no latency or savings claim; unknown provider codes still lose detail, static
candidate/policy/execution failures retain their existing reasons, and real AI recovery
success has not been measured.

Additional behavioral regressions cover a trusted Workflow binding that handles an
optional failed choice itself: success and subsequent uncertain execution must not carry
its old failure diagnostic. Prior effects are not undone by a later selection failure.

```sh
python benchmarks/diagnostics.py --output local-results/decision-diagnostics-ab.json
```

Use a full Git checkout with `.[dev]`; choose a new output file. CI runs this benchmark
on Python 3.10, 3.12 and 3.14. Source hashes bind the candidate report to its runtime.
Historical live browser evidence remains from 0.1.0; neither browser nor locked desktop
was retried for 0.1.2. Search indexing and AI citation remain unproven.

## Domain-neutral next-tool scope (0.1.3)

The core no longer imposes browser form requirements on every task. A host-owned
`decision_stage` marks loop tool and parameter calls; the tool question asks for the
next step and permits evidence/prerequisite actions without requiring them to complete
the whole goal. Direct record selection without the marker keeps its general selection
semantics. Task authors provide domain constraints, priorities and preconditions.

[Offline protocol A/B](tool-choice-offline-ab.json) and
[live next-decision A/B](tool-choice-live-ab.json) compare the exact published 0.1.2
source (`b51614e8acfbac5a64bbad3c7da34a5a3698fa27`) with the candidate. Six fixed
development cases span artifact handoff, record review, calculation dependencies,
read-only evidence, a synthetic form and explicit priority. Each has three tool choices
plus loop exits, tested in original and reversed candidate order with paired arm order.
The fixtures and expected-ID rationales are included. No held-out calibration is claimed.

The live experiment made 24 logical decisions and 24 network attempts. Every response
resolved to Jev 1.13.0, with complete reported usage. Both arms selected and admitted the
expected tool in 12/12 probes, including both permutations of the form case. There were
no provider failures or uncertainty reviews. Scope protocol checks change from 0/12 to
12/12; those checks describe request construction, not a gain in semantic accuracy.
The probes deliberately stop during binding, before intent or execution. Their
`max_steps/decision_probe_no_execution` terminals are not completed task claims.

There is no measured correctness gain here. Input tokens increase from 13,925 to
14,828 (903 more); both arms report 972 output tokens. Median complete probe time is
approximately 0.812 versus 0.810 seconds, too close in this small serial trial to claim
a speed improvement. Full benchmark time, per-probe timing, context bytes, raw choice,
admission, actual model and usage remain in the live report. At an explicitly supplied
input rate R USD/million, known input cost is `tokens * R / 1000000`; no current tariff
or invoice amount is assumed. Unknown or interrupted attempts remain unknown.

The offline answers are scripted and establish protocol/routing behavior only. New
behavioral regressions test final request scope, order-independent ID binding, private
parameter binding, direct-record compatibility and uncertain-attempt accounting.
Results do not establish full task, browser/desktop execution or general AI recovery.
Clear development descriptions may overstate quality on incomplete real contracts.

```sh
python benchmarks/tool_choice.py --output local-results/tool-choice-offline.json
# Opt-in, billable; configure a supplied private credential through the environment.
python benchmarks/tool_choice.py --live --output local-results/tool-choice-live.json
```

Use a full Git checkout and a new output path. The live runner reserves each dispatch,
checkpoints atomically, stops on provider/runtime failure, and never resumes uncertain
submissions automatically. CI runs only the offline mode. Native desktop acceptance and
search indexing remain unverified; no browser UI or desktop operation was repeated.

## Static task admission (0.1.4)

`check-task` now parses and compiles UTF-8 source without executing it, then checks for
an explicit top-level `workflow` assignment. An annotation without a value is not an
assignment. Compiler/parser warnings are projected to a fixed code and line number;
source excerpts and exception text do not become output. Non-UTF-8 input returns a
structured failure. Inference, prompts, tool execution and runtime gates are unchanged.

The [offline static A/B](static-check-ab.json) compares the exact published 0.1.3 source
(`37358ff83a83203b270c4cf92f8db7272239cca6`) with the candidate on 13 fixed synthetic
scripts, three paired repetitions each. Correct acceptance/rejection changes from 18/39
to 39/39. Combined classification and warning-count checks change from 15/39 to 39/39; baseline
non-UTF-8 input throws in three probes, while the candidate returns structured failures.
Both arms record zero inspected-script effects, source exposures and model calls.
Fixtures include parseable but uncompilable scope/control statements, duplicate
arguments, annotation-only exports, unknown imports, a possible file effect and a
nonfatal compiler warning. All source inputs and expected results are included.

Negative results and boundaries: compilation adds local deterministic work and returned
diagnostic bytes. A missing dependency, `workflow = None` or unreachable assignment can
still be accepted statically. This is not Task type-checking, import/dependency checking,
callback/provider validation, execution proof or a cross-version guarantee. Warning
policy can differ at runtime. Per-check elapsed times, context bytes, exceptions and
zero actual model usage remain in the report; no model savings or speed gain is claimed.

```sh
python benchmarks/static_check.py --output local-results/static-check-ab.json
```

Use a full Git checkout with `.[dev]` and a new output path. CI repeats offline checks
under Python 3.10, 3.12 and 3.14. No live Jev matrix, browser UI, locked desktop or URL
submission was repeated for this change. Native desktop and search indexing remain
unverified.

## Run configuration admission (0.1.5)

CLI `run` now parses and validates configuration before creating, registering or
loading the trusted task module. The engine shares the same pure validation: nonempty
goal, positive step/time budgets, object inputs/context, valid admitted message lists,
required-path syntax and finite UTF-8-encodable JSON. CLI explicit JSON `null` is rejected;
Python API omitted/None arguments still supply the documented defaults. Falsey values
of the wrong type no longer silently become defaults. Missing facts for a valid required
path remain the normal runtime `needs_context` outcome.

The [offline preflight A/B](run-preflight-ab.json) compares exact published 0.1.4 source
(`26cb69ae54e879043e6f18511da1f39446337de1`) with the candidate on 26 fixed synthetic
configurations, three paired repetitions each. Correct terminal classification changes
from 66/78 to 78/78; correct module-loading policy changes from 21/78 to 78/78. Baseline
invalid configurations create 57 synthetic import markers, while the candidate creates
zero. Both arms still load the valid script in nine probes, including three valid
missing-fact configurations that return `needs_context`. Reported configuration-failure
metadata, per-run timing, returned bytes and every outcome remain in the report.

Negative results and scope: preflight adds local validation and diagnostic bytes. Valid
configuration still loads caller-trusted Python and can have top-level effects; this is
not a sandbox or a module-safety guarantee. Archive, credential, runtime, workflow and
business conditions retain their existing validation. Static `check-task` remains a
separate non-executing compile/assignment check. The synthetic complete state needs no
model decisions; both arms use zero actual model/UI/network calls, and no cost or whole
task performance benefit is claimed. Shared validation also tightens wrong falsey SDK
types and invalid Unicode before observation/journal creation; the SDK None-default
and one-pass required-path cases have dedicated regressions.

```sh
python benchmarks/run_preflight.py --output local-results/run-preflight-ab.json
```

Use a full Git checkout with `.[dev]` and a new output path. CI runs only offline cases
under Python 3.10, 3.12 and 3.14. No previous live matrix, UI operation, locked desktop
or URL submission was repeated. Native desktop and search indexing remain unverified.

## Callback and provider admission (0.1.6)

The synchronous loop now rejects known coroutine, async-generator and generator
callbacks before invoking their bodies. Ordinary generator `Workflow.candidates` remains
supported. Kind checks cover callable objects and partial `.func` chains, while keeping
explicit synchronous wrappers intact. Choice providers are checked by binding two or
three positional arguments; optional keyword-only parameters no longer cause an
incorrect argument count. Dynamic providers retain their identity and bound resources;
static choices retain a deep-copied snapshot. Domains are still obtained afresh when
needed, without result caching. Fixed `contract_error` codes/roles/kinds help an AI repair
the script without exposing exception text or callable names.

The [offline callback A/B](callback-contract-ab.json) compares exact published 0.1.5 source
(`17fa46f76267da428f96f4ca4240a9a07de14b9a`) with the candidate on 24 fixed synthetic
fixtures, three paired repetitions with alternating arm order. Conformance to the new
local API expectations changes from 15/72 to 72/72. The baseline accepts all 45 deferred
or unsupported-provider admission probes; the candidate rejects them. Neither arm
invokes a callback body during admission. Positive fixtures cover two/three-argument
binding, optional keywords, resource-bearing callable/partial providers, static snapshots,
generator candidates and explicit synchronous wrappers. Native inference attempts and
actual model/UI/network calls are zero; each arm makes three scripted loop decisions.
Every result, expected value, exception type, context byte count and timing is retained.

Negative results and compatibility: compact fixture results grow from 12,258 to 18,885
bytes. The small mixed-fixture timings do not establish a speed benefit. If both two and
three positional arguments bind, three is now preferred; an optional/variadic provider
that previously received two may now receive bound parents. Use an explicit two-argument
wrapper when that older behavior is intended. The comparison includes this deliberate
migration boundary, so the conformance counts are not semantic accuracy measurements.
No model cost benefit is claimed.

Admission checks declarations and provider bindability, not every callback signature,
wrapper return type, bounded I/O or business behavior. Trusted module import may already
have effects before registration; `check-task` remains a non-executing static check.
Errors after execution starts remain uncertain and are not automatically retried.
This is still a synchronous runtime, not an async engine or a sandbox.

```sh
python benchmarks/callback_contract.py --output local-results/callback-contract-ab.json
```

Use a full Git checkout with `.[dev]` and a new output path. CI runs the offline fixtures
under Python 3.10, 3.12 and 3.14. No earlier live matrix, UI operation, locked desktop or
URL submission was repeated. Native desktop and search indexing remain unverified.

## CLI task output (0.1.7)

CLI `run` now discards writes to its redirected Python stdout/stderr during trusted
module creation/import and the loop. It retains only character and binary-byte counters,
not content or a console log. The final packet has optional `task_output` when writes
were nonempty. Other CLI commands, configuration admission and the SDK's `Engine.run`
retain their behavior. Tool returns and the engine's private observation/result journal
remain separate from console output.

The [offline output A/B](task-output-ab.json) compares exact published 0.1.6 source
(`32867087bf173515806958b61acffdd08c743659`) with the candidate on 19 fixed synthetic
fixtures, three paired repetitions with alternating arm order. Conformance to the new
console/exit policy changes from 6/57 to 57/57. Of each arm's 42 ordinary terminals,
exact JSON parsing changes from 12/42 to 42/42; the other 15 probes exit without a
terminal packet by design. Fixed synthetic stdout/stderr markers change from 51/30
occurrences to zero/zero. Streams restore in 57/57 probes in both arms. Native inference
attempts and actual model/UI/network calls are zero; each arm makes six scripted choices.
Raw captured output stays inside each trial; the report stores only digests and counts.

Fixtures cover import, observation, verification, successful/uncertain effects, import
errors, Unicode, invalid-UTF-8 binary writes, empty and large writes, warnings, return
counts and task interruptions. Diagnostic recovery of a trailing baseline packet is not
counted as directly parseable output. The benchmark catches interruptions before the
interpreter prints them; its exception-marker counts alone do not prove interpreter
privacy. Separate real CLI subprocess regressions reproduce exception/source-text
exposure and false successful exit codes, then verify quiet nonzero exits. Effect
interruption regressions independently confirm one effect, retained intent, no terminal
or fabricated safe failure, and no automatic retry.

CLI task `KeyboardInterrupt` now raises quiet `SystemExit(130)`. Task `SystemExit` keeps
exact integer codes 1..255; text, zero, None or other codes become 1. There is no verified
terminal packet or returned counters on these exits; possible runtime effects and usage
still require reconciliation. The SDK and parser/help exits are unchanged.

Negative results: console debug text is discarded and cannot be recovered. Total returned
bytes change from 3,016,230 to 19,906, dominated by the deliberately large synthetic
output. Excluding that fixture, bytes increase from 15,212 to 18,454 because of metadata.
The mixed-fixture median time increases slightly; no speed, semantic-quality or model-fee
benefit is claimed. Counters count Unicode code points and buffer bytes separately,
without text encoding. This is a count-only sink, not a complete BufferedIO emulator.

The redirect is process-global and cannot isolate overlapping tasks or threads. Saved
streams/logging handlers, OS descriptors, subprocesses and explicit file logs can bypass
it; redirected streams do not support `fileno()`. There is no sandbox, all-output privacy
or unconditional terminal-JSON guarantee for arbitrary trusted Python.

```sh
python benchmarks/task_output.py --output local-results/task-output-ab.json
```

Use a full Git checkout with `.[dev]` and a new output path. CI runs only offline fixtures
under Python 3.10, 3.12 and 3.14. No earlier live matrix, UI operation, locked desktop or
URL submission was repeated. Native desktop and search indexing remain unverified.


## CLI argument failures (0.1.8)

When argparse reports an error in any command parser, the CLI now returns one fixed
JSON packet with `failed`, phase `arguments`, code `invalid_command_arguments`,
`script_loaded: false` and `model_calls: 0`, then exits 2. Direct `main` returns 2.
It exports no raw error text, argv values or usage. Parsing precedes command dispatch,
task source access and trusted module loading. Successful parsing still uses the
separate `configuration` phase for malformed JSON or invalid run configuration.

The [offline argument A/B](cli-arguments-ab.json) compares exact published 0.1.7 source
(`609d76822dc721a1f19bb7c3b2837f553507d24f`) with the candidate on 25 fixed synthetic
argv fixtures, three paired repeats with alternating arm order. Conformance to the new
interface policy changes from 27/75 to 75/75. Each arm has 48 parser-failure probes,
nine human help probes and 18 other offline/valid/configuration probes. Exact JSON
packets change from 18 to 66; the nine help results remain text and exit 0. Fixed
synthetic stderr markers change from 24 occurrences to zero. Both arms restore streams
in 75/75 probes and make zero actual model/UI/network calls.

For all 48 parser failures in both arms, measured task source reads, module-spec/exec
attempts and new files remain zero. This is a preserved property, not an execution-safety
gain attributed to the change. Positive fixtures verify spec, static checks, exclusive
initialization, already-complete runs, legal long-option abbreviations and malformed
JSON configuration. Valid runs deliberately import a local synthetic marker, and require
no tool or model decisions. Real CLI subprocess regressions additionally verify exact
JSON, exit code 2 and absence of raw stderr for an invalid integer value.

Negative results: specific argparse repair details are discarded. Total returned bytes
change from 39,492 to 34,578, while the non-parser fixtures grow from 26,319 to 27,810
because the machine spec now explains this boundary. Mixed small timings and individual
slower fixtures remain in the report; no speed, semantic-quality or model-fee benefit
is claimed. Normal string argv is supported, not arbitrary Python objects. Argparse can
temporarily construct raw diagnostic strings, so output suppression is not memory
zeroization or a sandbox.

Help preserves its original precedence and displays `prog`. It can exit before checking
a later unknown token; not every command containing a bad token produces JSON. Quiet
runtime interruptions still have no terminal packet and require effect/usage
reconciliation. Failed output streams and arbitrary process failures remain outside
this parser boundary. The SDK and Jev's tool/parameter decisions are unchanged.

```sh
python benchmarks/cli_arguments.py --output local-results/cli-arguments-ab.json
```

Use a full Git checkout with `.[dev]` and a new output path. CI runs the offline fixtures
under Python 3.10, 3.12 and 3.14. No earlier live matrix, UI operation, locked desktop or
URL submission was repeated. Native desktop and search indexing remain unverified.

## Bilingual site and discovery baseline

The [bilingual-site report](geo-bilingual-2026-10-11.json) records a prepublication local
build of 16 English/Chinese pages, language counterparts, project identity, FAQ, case
evidence and a frozen brand/nonbrand query set. The sampled baseline did not return an
official Harness URL; this is not proof of index absence. HTTP delivery, crawl, indexing,
query discovery, AI citation and adoption are separate stages. No exposure or ranking
improvement is established by a successful build or IndexNow receipt.

## Observable loop context budget (0.1.9)

The loop still admits shared context by the existing 15,000 serialized JSON-character
limit. Exactly 15,000 is included; only a larger `len(json.dumps(context,
ensure_ascii=False))` is rejected, with the original default separators. This unit is
Unicode code points of the serialized JSON, including escaping and punctuation; it is
not UTF-8 bytes, raw string length or model tokens. The spec now exposes this threshold
and scope. A rejection adds count-only `context_budget` metadata with fixed scope,
stage, unit, limit and observed length. Returned loop calls add `context_characters`
and `context_character_limit` beside the existing UTF-8 `context_bytes` measurement.

The [offline budget A/B](context-budget-ab.json) compares exact published 0.1.8 source
(`c757179c22e6104df06a44e8ce66e5217f1d96c7`) with the candidate on 14 fixed synthetic
fixtures, three paired repeats with alternating arm order. Both arms preserve all 42/42
expected behaviors and exact pairwise status/decision/effect parity. Each arm has 18
scripted completed loops, 18 expected reviews and six admitted direct-decision probes,
with 33 scripted choices, 18 effects and 18 intents. New measurement/diagnostic
expectations change from 6/42 to 42/42; these are host protocol checks, not semantic
accuracy improvements. All requested shared-context character/UTF-8 byte counts stay
identical between arms. Native attempts and actual model/UI/network calls are zero.

Fixtures cover ASCII, Chinese and emoji, exact/over-limit projection and selection,
the extra stage marker, parameter additions, and direct `Engine.decide` compatibility.
A 15,000-character projection can exceed the limit after the tool-stage marker is added;
parameter context can exceed it after an earlier selection. Unicode probes show only
that the loop's character admission remains intact with larger UTF-8 measurements;
scripted completion does not prove that real provider payload limits admit those inputs.
Separate regressions preserve unknown prior usage, completed steps/spent calls, trusted
binding recovery and execution uncertainty after an effect. A refused decision does not
imply zero calls or effects for the entire run.

Negative results: terminal/context output grows from 15,414 to 19,692 bytes. Mixed
median time increases slightly; no speed, model-quality or fee benefit is claimed.
The budget covers admitted shared context: policy output plus remaining budgets before
selection, then host stage and parameter-context additions. Candidate record text,
selection question and full prompt are outside this measurement. Direct decisions retain
their separate upstream spec/provider limits. Existing provider question/state/body
limits remain in force; this is not a total payload, token, cost or memory budget.
No context is silently truncated or cached. Only scalar measurements become diagnostics;
raw context stays out of the terminal. Exceptional inference paths may lack returned-call
measurements and continue to preserve unknown usage.

```sh
python benchmarks/context_budget.py --output local-results/context-budget-ab.json
```

Use a full Git checkout with `.[dev]` and a new output path. CI runs offline fixtures on
Python 3.10, 3.12 and 3.14. No earlier live matrix, locked desktop or URL submission was
repeated. Native desktop completion and search indexing remain unverified.


## Typed request-planning handoff (0.1.10)

An empty native Choice plan now preserves its typed `NEEDS_NARROWING` or `NEEDS_CONTEXT`
status and reports fixed planning reasons. Unknown statuses become `UNAVAILABLE` with
`request_planning_review`; raw status/error text is not exported. Optional
`telemetry.planning` (or a loop call’s `planning`) has scope `current_selection`, phase
`request_planning` and `inference_dispatched: false`. This is generated only on the
host’s actual empty-plan path, before the native batch dispatcher. Selection diagnostics
retain the host tool/parameter stage and fixed planning codes.

The [offline planning A/B](planning-diagnostics-ab.json) compares exact released 0.1.9
(`bb808e1472d3894e276689115574f126c193c52a`) with the candidate on 14 fixed fixtures,
three paired repetitions with alternating arm order. Final status/selection/effect,
dispatch and usage behavior remains 42/42 correct in both arms, with pairwise parity.
New diagnostic/measurement conformance changes from 12/42 to 42/42. Deliberate typed
status corrections on three fixtures/nine rows are counted separately (33/42 to 42/42),
not as model accuracy improvements. The candidate returns 30 deferred-call planning
records. Both arms make 18 mock batch dispatches, 21 MockTransport attempts and three
synthetic effects/intents; actual model and network calls are zero.

Fixtures exercise real pinned planner fit checks with large ASCII/Chinese records,
254 choices and missing required record fields, tool and dependent-parameter deferral,
previous unknown usage after a mocked retry, trusted fallback, unknown/injected planner
status, generic full-spec validation and HTTP 413. Nine rows preserve unknown mock usage.
The only retry is the SDK’s existing bounded policy. Deferred parameter selection does
not erase an earlier call or unknown usage; fallback clears a current failure diagnostic
while retaining historical planning metadata, and later effect errors remain uncertain.
Separate regressions preserve empty-record completion and strict fixed-code projection.

Negative results: returned output grows from 33,295 to 37,777 bytes. Some local fixtures
become slower; mixed small timings establish no speed, semantic-quality or fee gain.
The planner’s limits, fit rules, prompts, actual inference and loop context cap are
unchanged. This is not a new input-size ProviderError taxonomy: the pinned SDK emits
these typed deferrals from planning. Generic `ValueError` remains generic, and an
already dispatched HTTP 413 remains `http_413_body_suppressed` with unknown usage.
No exception-message matching or blind retry is introduced.

The no-dispatch/known-zero statement applies only to that selection. Earlier calls,
unknown billing and effects may exist in the same run. Absence of `planning` does not
prove dispatch. Keep goal/safety constraints intact while the primary AI narrows
program-supplied candidates/descriptions or supplies required context. Model selection
still provides neither permission nor completion proof.

```sh
python benchmarks/planning_diagnostics.py --output local-results/planning-diagnostics-ab.json
```

Use a full Git checkout with `.[dev]` and a new output path. CI runs only offline cases
under Python 3.10, 3.12 and 3.14. No paid model matrix, locked-desktop retry or URL submission
was repeated. Native desktop completion, crawler visits, indexing and AI citations remain
separate unverified evidence layers.

## Current action identity on uncertain stops (0.1.11)

An execution-window `DecisionStop` now returns `execution_uncertain` with the current
pending bound `action_id` when available. This window covers execute, result admission,
immediate observation and unchanged-state verification. The runtime does not infer an ID
from history or attach a cleared ID to a later-cycle stop. Ordinary exceptions already
carried pending IDs. The identifier helps locate private journal evidence and reconcile
the target; it proves neither effect success nor execution count, is not an idempotency
key and does not permit rerunning. No bound arguments are added to this terminal field.

The [offline identity A/B](execution-identity-ab.json) compares exact published 0.1.10
source (`c4486ed8cc3c82a00f421f3bac32653b814f2d40`) with the candidate on 16 fixed
synthetic fixtures, three paired repeats with alternating arm order: 48 rows per arm.
New identity conformance changes from 21/48 to 48/48. Both arms retain 48/48 expected
status/reason/step/effect/intent/dispatch/usage behaviors with exact pairwise parity;
this is an interface repair, not semantic-quality improvement. Each arm has 30 uncertain
exits; the candidate adds the current ID to 27 `DecisionStop` rows, while three
ordinary-exception rows already had it. Both arms have 51 scripted choices, 42 effects/intents and 21 rows with
unknown scripted usage. Native inference attempts and real model/network/UI calls are zero.

Fixtures cover the four execution-window stages with known/unknown prior scripted usage,
pre-execution stops, existing ordinary-exception identity, verified completion, a
later-cycle stop after pending was cleared, and a second action whose ID must not be
replaced by its predecessor's. Independent synthetic effect counters and durable intent
identify the current action. Separate CLI regressions check exit 2, a single local effect
marker, preserved identity/unknown usage and discarded print output. These do not establish
real-world target reconciliation or external exactly-once behavior.

Negative results: returned context grows from 24,069 to 24,897 bytes (+828); the mixed
whole-operation median rises from about 1.371 to 1.463 ms. Individual slower fixtures
remain in the report. Timings include synthetic registration, loop admission, scripted
selection, callbacks, effects and journal serialization, excluding process/import setup
and terminal/source-hash analysis. Scripted usage is separate from real model usage;
unknown scripted usage is not cleared by identifying the action. Authorization and retry
policy are unchanged; no speed, model-quality or fee benefit is claimed.

```sh
python benchmarks/execution_identity.py --output local-results/execution-identity-ab.json
```

Use a full Git checkout with `.[dev]` and a new output path. No paid model matrix, browser
operation, locked-desktop retry or URL submission was repeated. Native desktop completion,
crawler visits, indexing and AI citations retain their separate evidence limits.

## Transport counters owned by the run (0.1.12)

Existing `telemetry.requests` and per-call `transport` evidence are retained: native
Choice counts logical packed requests. Optional `telemetry.owned_transport` separately
captures the owned provider client's `Client.stats` deltas from Session start to terminal
finish, before the journal's terminal write and client close. It reports SDK
`request_attempts` (including retries), HTTP client-object creation/reuse and
`counters_complete`, with fixed ownership/snapshot scope. Starting/ending counters must
be exact nonnegative integers; the finish must not fall below the start or a witnessed Session.run value;
missing/invalid/decreasing fields become null rather than zero. This does not detect every
unobserved reset. No active owned Session means omitted metadata, not zero ownership proof.

The [offline counter A/B](transport-counters-ab.json) compares exact published 0.1.11
source (`95276bd77eef162645b45bfcd8c40c7a06dac212`) with the candidate on 16 fixed
synthetic fixtures, three paired repetitions with alternating arm order: 48 rows per arm.
New snapshot conformance changes from 6/48 to 48/48; both arms retain 48/48 expected
behaviors with exact pairwise parity. The candidate has 42 owned snapshots, including
12 with partial unknown counters; six inactive/standalone rows omit metadata as required.
Both arms retain 42 logical requests, 45 operation MockTransport entries plus three
excluded seed entries, 27 synthetic effects and 15 rows with unknown mock usage. Real
model/network/UI calls and forbidden real transport attempts are zero. These are protocol
checks, not semantic-quality gains.

The initial offline report and its matching source were retained locally. This published
report was rerun after clarifying the spec's fixed snapshot literal and separate timing
description; runtime counter behavior and all case/count expectations remained unchanged.

Fixtures exercise retries, credential rejection, nonzero starting counters, nullable
invalid/bool/string/negative fields, a reset below a witnessed high, fixed-key projection,
early terminals, inactive ownership and unchanged failure/usage handling. A separate SDK
encoding counterexample records one attempt and zero MockTransport handler entries; it
does not produce an Engine terminal snapshot. This demonstrates why the SDK counter is
not an HTTP-dispatch count. A seeded operation is outside the run-owned deltas. One
logical request can have three SDK attempts after retries or none on credential rejection.

Negative results: returned context grows from 45,627 to 53,319 bytes (+7,692); the mixed
whole-operation median rises from about 1.660 to 1.698 ms, with slower local fixtures
retained. Timing includes loop admission, pinned planning, bounded mock retry/validation,
effects, snapshotting and journal flush/fsync; it excludes process/import/client/task
setup, seed operations and post-call analysis. Complete counters do not make unknown token
usage known. Attempts prove neither HTTP delivery, server receipt, inference nor billing;
HTTP client objects/reuse are not TCP connections, and other tool traffic is excluded.
Model identity, authorization, execution, exit and retry handling are unchanged. No
real-provider measurement, speed, model-quality or fee benefit is claimed.

```sh
python benchmarks/owned_transport.py --output local-results/transport-counters-ab.json
```

Use a full Git checkout with `.[dev]` and a new output path. No paid model matrix, browser
operation, locked-desktop retry or URL submission was repeated. Historical acceptance
and GEO claims retain their existing scope.
