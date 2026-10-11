# Jev Harness use cases

Jev Harness lets an AI define reusable tools and a goal, then delegate exploration to Jev.
The route, relevant sources and later parameters can be unknown when the task starts.
The AI writes tool, observation, completion and resource contracts; Jev decides which
tool and parameters to use next, whether to continue, and when to stop. Code collects,
executes and independently verifies the result.

[Historical demos](https://apixly-ai.github.io/jev-harness/#browser-evidence) ·
[中文](use-cases.zh-CN.md) · [Task protocol](agent-contract.md)

The three cases below are **designs with acceptance pending**, not completed runs or
bundled commands. Tool names illustrate interfaces the task author registers. Candidate
lists are refreshed from observations and admitted results at each step; they do not
require a complete route or a next-step router written by the AI.

## Browser: research through an unknown multi-page route

**Design; acceptance pending.** Give the task an entry URL and a goal such as: “Find three
self-hosted tools that meet the supplied requirements and save a comparison with
checkable sources.” The task discovers links, sections,
filters and dependencies as it browses. Jev chooses whether to explore another source,
read a detail, compare evidence or save the dossier.

| Contract | Task definition |
| --- | --- |
| Input | Entry URL, goal, tool requirements, allowed sources and time/step budget |
| Reusable tools | `discover`, `open`, `read`, `compare`, `collect_evidence`, `save_dossier` |
| Dynamic parameters | Newly observed links, sections, source pairs and evidence references; child choices depend on the selected source/control |
| Observation | Current page, discovered frontier, admitted evidence and unresolved prerequisites |
| Completion | Three distinct tools, every supplied requirement supported by captured sources, and a saved comparison whose citations match those sources; missing support remains unresolved |

For example, reading a source can reveal a prerequisite that was absent at startup;
opening its reference exposes another parameter domain. Tool providers supply the
currently usable candidates and preconditions. They do not choose the next branch.
The same tools should work across different layouts and source paths.

The acceptance design uses the **same script** against three blind portal variants:

1. A successful route that discovers applicable tools through one set of sources.
2. Another successful route with changed links and a prerequisite discovered only after
   reading a page, requiring a different exploration trace.
3. A missing-source variant that cannot establish the required evidence and must retain
   gathered evidence and an unresolved terminal result.

The task and its providers must not read the fixture answer or hidden route. An independent
acceptance verifier checks sources and the saved artifact separately. Future real Jev and
headless Camofox acceptance should retain newly discovered candidate sets, selected tool
parameters, different route lengths, failed branches and actual model/usage evidence.
Empty-domain or evidence-limit stops remain visible; this design does not assume automatic
recovery. No real exploration result has been recorded for this case yet.

## Repository: investigate a failure through read-only tools

**Design; acceptance pending.** Given a repository entry and a test or CI failure, locate
the relevant execution path and save an explanation with inspectable source evidence.
The relevant files, symbols and hypotheses are discovered during the run.

| Contract | Task definition |
| --- | --- |
| Input | Repository scope, recorded failure, investigation goal and resource budget |
| Reusable tools | Search code, read files/symbols, inspect existing test/log artifacts, compare evidence and save a diagnosis |
| Dynamic parameters | Paths, symbols, line windows and evidence references found by earlier reads |
| Completion | Independently checked source revisions/citations and a saved diagnosis supported by the failure evidence; unresolved claims remain for review |

The tools read code and existing artifacts without modifying the repository or executing
its programs; the diagnosis is saved to a caller-owned output location outside the source
tree. Jev chooses what to inspect next; the task author supplies no file-by-file route.
Exact path filtering and extraction stay in code.

## Controlled API: diagnose an incomplete task

**Design; acceptance pending.** Starting from an authorized test-service entry, determine
which prerequisite or state transition prevents a task from completing and save an
evidence-backed diagnosis. Resource links, schemas, event pages and dependencies become
known through responses.

| Contract | Task definition |
| --- | --- |
| Input | Authorized service entry, task goal, read-only scope and resource budget |
| Reusable tools | Discover resources, read status/schema/events, compare observations and save a diagnosis |
| Dynamic parameters | Response-discovered resource IDs, schema references and pagination cursors; dependent choices follow the selected resource |
| Completion | Independent service-state/event checks and a saved diagnosis linked to those observations |

Jev selects which evidence to request and when enough is available. The program validates
read operations and binds only supplied resources. Missing evidence remains unresolved;
this case does not repair or mutate the service.

## Candidate generation and exploration

The current native loop selects candidate references; it has no builtin free-text
generator. Queries, prose or new candidate structures can come from a registered trusted
generator or the primary AI. Validate its output before admitting it to a candidate pool;
Jev then chooses the tool and candidate to use. Generated text must not directly become
executable code, commands or selectors. The primary AI authors or extends the contracts;
it does not route every next step on Jev's behalf.

## Historical connection evidence

The earlier form and Counter show that tool selection, binding and execution were
connected. They remain reproducible evidence with their original scope; they do not
establish the three open-route designs above.

### Browser: prepare and verify a local travel draft

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

### Python: select a tool and bind an amount

This Counter is a historical connection example. Exact arithmetic normally belongs in
code; the small task illustrates the parameter interface rather than open-route research.

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

### Runtime: continue from evidence and stop repeated effects

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

Choose Harness when reusable tools can expose useful next steps, observations and
candidate domains can evolve, and completion can be checked independently. Bound the
resources and executable interfaces while allowing the exploration route to remain
unknown. Keep exact deterministic work in code; the primary AI owns tool/task authoring
and free-form generation, while Jev owns repeated tool/parameter decisions. Jev Filter
provides the inference/platform dependency.

The new designs have not established task success, speed or fee advantages. Historical
browser evidence retains its local-fixture scope; native desktop completion remains
unverified. Read the task and context contracts when defining your own completion and
handoff conditions.

[Frequently asked questions](faq.md) · [Architecture](architecture.md) ·
[Acceptance evidence](../reports/README.md)
