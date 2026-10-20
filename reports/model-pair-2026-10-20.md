# Jev 1.14.0 against 1.13.0 on unchanged harness code — 2026-10-20

TypeSafe released Jev 1.14.0 on 2026-10-14. On 2026-10-20 the `jev-preview` alias points to
it and `jev-latest` still points to 1.13.0 (docs.typesafe.ai/models). Price and context
limits are unchanged ($0.042 per million input tokens, output free; 64k per request, 32k
per question). New in 1.14 are images and the Box question type, both behind an opt-in
`TypeSafe-Danger-Zone-Images` header; the harness sends neither.

**Result: 1.14.0 is a drop-in for next-tool selection, but under the unchanged 0.55
top-probability floor it stopped a parameter choice for review in 3 of 5 runs. The default
stays `jev-1.13.0`; 1.14.0 is available by explicit selection.**

| Receipt run, 3 repeats, model order alternated | jev-1.13.0 | jev-1.14.0 |
|---|---:|---:|
| Next-tool decisions selected and admitted (6 cases x 2 orders x 3) | 36 / 36 | 36 / 36 |
| Two-stage counter task completed in the fewest calls | 3 / 3 | 2 / 3 |
| Parameter decision: top probability (correct value each time) | 0.76, 0.65, 0.75 | 0.57, 0.51, 0.56 |
| Parameter decision: probability on REVIEW | 0.06, 0.07, 0.06 | 0.25, 0.27, 0.28 |
| Stops for review (`below_min_top_probability`) | 0 | 1 |
| Lowest next-tool top probability | 1.00 | 0.99 |
| Median next-tool operation time | 0.462 s | 0.463 s |
| Reported usage (input / output tokens) | 53,043 / 3,453 | 51,981 / 3,388 |

An earlier development run (2 repeats, same code, before the counter receipt kept full
probabilities) gave the same picture: 24 / 24 next-tool decisions on both models, the
counter task 2 / 2 on 1.13.0 and 0 / 2 on 1.14.0, whose parameter top probabilities were
0.52 and 0.45. [Development receipt](model-pair-2026-10-20-dev.json) ·
[receipt](model-pair-2026-10-20.json).

## What the evidence supports

- **Next-tool selection does not regress.** Both models chose and the harness admitted the
  expected tool in 60 of 60 decisions each across both runs, with top probabilities of
  0.99 or more. These fixtures were already saturated on 1.13.0, so this shows no
  regression, not an improvement.
- **The parameter stage shifts toward REVIEW.** On the counter task (goal: reach 3 with the
  fewest increments; offered increments 1 and 2), 1.14.0 always ranked the correct value
  first but, in the receipt run, put 0.25–0.28 of the probability on REVIEW. Its top
  probability sat at 0.45–0.57 against the 0.55 floor tuned on 1.13.0, so admission
  flipped from run to run. Identical requests returned different probabilities on both models (1.13.0
  ranged 0.65–0.76), so a single run cannot settle admission near the floor.
- **Why the default stays.** The hosted floors (`min_top_probability` 0.55,
  `min_margin` 0.10) were tuned on 1.13.0, and TypeSafe's own stable alias still names
  1.13.0. Switching would turn some correct parameter choices into review stops.

## What changed in the harness

- Every harness-built request now names a versioned model. The default is `jev-1.13.0`
  (`backend.DEFAULT_MODEL`); select another with `AgentLoop(model=...)`,
  `Engine(model=...)`, `ToolkitSession(model=...)`, or `--model` on `jev-harness run` and
  `jev-harness mcp`. An explicit `analysis_spec["model"]` on `Engine().decide` still wins and stays the
  caller's responsibility (not validated).
- Moving aliases (`jev-latest`, `jev-preview`) and malformed IDs are rejected before any
  call; the CLI reports `invalid_run_configuration` without loading the script. An alias
  can change answers without a code change, which the docs advise against once confidence
  thresholds are tuned.
- Telemetry already recorded `model_requested` and `model_resolved` per call; both runs
  resolved to exactly the requested ID.
- `benchmarks/model_pair.py --live` reproduces this pair for any two versioned IDs.

## Limits

Six synthetic development cases and one two-stage task; 5 parameter decisions per model.
No held-out set, no calibration study, no browser or desktop run, and no retuning of the
floors or the parameter question for 1.14.0. Whether a lower floor or a reworded parameter
question would admit 1.14.0's choices without admitting wrong ones is not measured.

## Usage

Both runs: 88,403 input / 5,755 output tokens on 1.13.0 and 85,228 / 5,560 on 1.14.0, all
reported (no unknown attempts); about $0.0073 in total at the published input price. Five
small exploratory requests made before the runs to resolve the aliases (four answered, one
rejected as an unknown model ID) are not in the receipts.
