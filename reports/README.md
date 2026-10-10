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
