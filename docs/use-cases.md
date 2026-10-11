# Jev Harness use cases

Jev Harness is Apixly’s independent Python runtime for bounded agent tasks. Your program
supplies registered tools, parameter candidates and a completion check; Jev chooses the
next tool and candidate references. The program executes and independently verifies the
result. The examples below show three different seams of that contract.

[Watch the interactive demos](https://apixly-ai.github.io/jev-harness/#showcase) ·
[中文](use-cases.zh-CN.md) · [Task protocol](agent-contract.md)

## Browser: prepare and verify a local travel draft

**Goal:** prepare a draft for Mira, traveling to London with flexible dates. The program
owns the page, allowed origin, supplied values and authorization policy. The browser
adapter exposes observed controls as candidates; it does not give the model arbitrary
selectors, scripts or generated form values.

| Contract | Supplied or independently observed value |
| --- | --- |
| Input | Traveler Mira, destination London, flexible dates enabled |
| Choices | Observed controls and dropdown options; supplied named text values |
| Operations | Fill traveler, select destination, toggle flexibility, prepare draft |
| Completion | Unique observed control values and final text `Draft ready: Mira \| London \| flexible=true` |
| Scope | Local synthetic fixture; no real booking or message |

<figure><video controls muted playsinline preload="none" poster="../web/media/browser-poster.webp"><source src="../web/media/browser-demo.mp4" type="video/mp4"></video><figcaption>Current screenshots replay the original fixture sequence. This is a screenshot replay with zero new inference calls, not a newly recorded Jev run.</figcaption></figure>

Historical **v0.1.0** acceptance used real Jev and headless Camofox and completed this
fixture in **four tool executions**. Early review and authorization-gate outcomes remain
in the [acceptance ledger](../reports/README.md) and
[machine-readable evidence](../reports/acceptance.json). A successful small fixture does
not establish open-web or production task success.

The [unchanged fixture](../examples/fixtures/form.html) and
[media generator](../scripts/generate_showcase.py) make the display reproducible. In a
repository checkout with an active named headless Camofox service, ffmpeg and cwebp:

```sh
python scripts/generate_showcase.py
```

The media generator uses exact program operations and checks the final controls/text;
it makes no model calls. Its [provenance manifest](../web/media/showcase.json) records the
fixture digest, media digests and verified fields. See [browser adapters](adapters.md)
for the real task interface and caller authorization requirements.

## Python: select a tool and bind an amount

**Goal:** advance an observed counter from zero to the supplied target three without
overshooting. The task describes the increment tool and provides valid amounts from the
current state. An illustrative sequence is `0 → 1 → 3`; actual selected steps depend on
the decision run.

| Contract | Program-owned value |
| --- | --- |
| Input | Current value and target `3` |
| Choices | Amount `1` or `2`, excluding values that overshoot |
| Execution | A registered Python tool increments the actual state |
| Completion | The independently observed value equals the supplied target |

Start from the runnable scaffold in an environment with the exact
[Git installation](agent-contract.md#install-and-run-your-first-task). These first three commands make no model
calls; the last is billable and requires your supplied `TYPESAFE_API_KEY` or
`TYPESAFE_API_KEY_FILE` in the environment.

```sh
jev-harness spec
jev-harness init-task task.py
jev-harness check-task task.py
jev-harness run task.py --goal 'Reach target without overshooting' --inputs '{"target":3}'
```

Historical generated-task acceptance and the small generic/conditional prompt A/B are
recorded in the [evidence ledger](../reports/README.md). The homepage’s counter graphic is
an illustration, not an inference recording. Passing a syntax check does not prove
runtime validity, and trusted Python imports can have effects.

## Runtime: continue from evidence and stop repeated effects

**Goal:** continue when an admitted tool result provides new useful evidence, and block
an identical action against the same decision state before executing it again.

| Contract | Program-owned value or check |
| --- | --- |
| Context | Current observation, admitted result summary and action ledger |
| Choices | Registered tools with supplied argument candidates |
| Continuation | A useful `result_context` summary can advance the next decision |
| Completion | The independent verifier passes; a model claim alone is insufficient |
| Repetition | Same observation, action ID and actual parameters stop with `blocked/repeated_action_state` |

The [offline evidence-progress report](../reports/evidence-progress-ab.json) uses fixed
synthetic decisions. Expected outcomes include blocking and configuration rejection as
well as completion. It establishes those contract behaviors, not live semantic quality
or a general speed/cost gain. Reproduce it from a full checkout with development extras:

```sh
python benchmarks/progress.py --output local-results/my-progress-ab.json
```

Raw tool results that are not admitted cannot advance an unchanged observation. Polling
against a fixed observation is unsupported; a tool must bound its own polling or expose
meaningful progress. The runtime does not provide cross-run resume or exactly-once
business effects. Read [context management](context.md) and the
[task protocol](agent-contract.md) before adapting these cases to your own system.

## Choosing a suitable task

Choose Harness when a useful next step can be expressed as registered tools and supplied
candidates, observations can be refreshed, and an independent success check exists.
Keep exact deterministic work in code. Keep open-ended planning and writing in the
primary AI. Jev Filter handles repeated semantic screening over many records; Harness
reuses it as the inference/platform dependency for bounded execution loops.

Browser and desktop are generic adapters. Native desktop completion remains unverified,
and the desktop must be unlocked with the required permissions. No universal success,
model-fee savings, sandbox isolation or cross-run idempotency is claimed.

[Frequently asked questions](faq.md) · [Architecture](architecture.md) ·
[Acceptance evidence](../reports/README.md)
