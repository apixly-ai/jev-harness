# Cold task authoring and native operation — 2026-10-12

Both actors completed the factual repository investigation with direct shell/Python.
The optional-harness actor also had a caller-authored `run_script` entrypoint backed by
real Jev inference, but did not create or execute a harness task file. This small eight-file,
approximately 2 KB checkout does not establish an authoring benefit or natural preference.

| Arm | Actual route | Factual source evidence | Whole operation | Harness authoring |
|---|---|---|---:|---|
| Direct control | Container shell/Python | Pass after explicitly marked shape adaptation | 99.773 s | Not applicable |
| Same native tools + optional Jev Harness | Container shell/Python | Pass in original format | 95.216 s | No task file created |

This is ordinary sh/Python in a real Docker container, carried over MCP, **not the Codex
built-in host shell**. The actors have the same goal/corpus/output scope. The optional
arm additionally sees the installed public SDK and script-execution capability. No solution
script exists initially, no product skill or prompt specifies a preferred route, and
native script automation is allowed in both arms.

The real zero-model canary verifies network-none execution, read-only corpus/runtime,
empty initial work, output writes, and absent oracle/credential/Docker-socket mounts.
The model-facing shell has no host shell. Execution freezes caller script bytes into a
separate protected worker; model credentials stay in a host-only bridge. The bridge has
explicit live opt-in, schema/byte/request/deadline limits, no automatic physical-request
retry, actual per-model usage and unknown-submission retention. The actors never invoked
it in these two turns, so actual Jev inference was zero.

## Output-contract correction retained

The initial prompt listed quote fields and categories, but omitted the exact flat
`records` envelope and label enum. The direct control produced explicit category groups
with descriptive labels, so the original flat-format evaluator rejected it. This is an
undocumented format assumption, not evidence that native reasoning failed.

A controller-only, explicitly posthoc adapter flattens those goal-named category groups
and maps their labels. It preserves all original source, quote, character windows and
full-source hashes. Original format rejection and original files remain unchanged.
Source-authenticated scoring then passes all three categories, version identity and the
closed fixture state-transition checks. The optional arm's original flat records already
pass. Header-only, mixed/unknown groups, label conflicts and fabricated provenance remain
rejected by regression tests.

The actor prompt now states exact `records`, field names, label enum, Unicode/end-exclusive
windows and full-source UTF-8 SHA-256. No paid run was repeated to erase the mismatch.

## Usage and scope

The CLI requested `gpt-6.1-sol`; resolved provider identity remains unknown. Direct control
reported 126,206 input, 104,192 cached-input subset and 2,203 output tokens. Optional-harness
reported 129,609 input, 89,472 cached-input subset and 2,384 output tokens. Both terminal
protocols qualified with zero unexpected activity. Pricing/invoice charges are unknown.

Whole-operation timings include the primary turn, capability discovery, native Python
writing/execution, server bootstrap and final response. Harness authoring time is not
applicable; an absent task file is not a zero-time authoring advantage. This one pair is
not a success-rate or latency claim. See [receipts](cold-authoring-2026-10-12.json),
[prepared-task choice evidence](adoption-2026-10-12.md) and `benchmarks/cold_authoring.py`.
