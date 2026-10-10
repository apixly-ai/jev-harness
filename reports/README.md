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
