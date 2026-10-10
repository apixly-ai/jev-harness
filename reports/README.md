# Acceptance evidence and scope

The runtime is the product; these cases test reusable seams rather than special-case
features. All inputs are local synthetic data. No bookings or messages were sent.

Current browser acceptance: real Jev 1.13.0 with Camofox in a named headless session,
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
