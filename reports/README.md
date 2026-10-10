# Acceptance evidence and scope

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
