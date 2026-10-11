# Jev Harness FAQ

[简体中文](faq.zh-CN.md) · [Project overview](../README.md) · [Task contract](agent-contract.md)

These answers describe Apixly's Jev Harness v0.1.12. They distinguish the runtime's
contracts, historical live evidence and illustrative media so readers can check each claim.

<a id="what-is-jev-harness"></a>

## What is Jev Harness?

Jev Harness is a Python runtime for AI-authored, bounded task scripts. The primary AI
defines the task and registers tools; Jev chooses the next registered tool and its
program-supplied parameter candidates. The program executes that bound action and
independently checks whether the goal is complete. It supports semantic branching within
explicit limits. See the [project overview](../README.md) and [architecture](architecture.md).

<a id="project-identity"></a>

## Is this an official TypeSafe AI product or the PyPI jev-harness package?

No. This is independent community software maintained by Apixly at
[apixly-ai/jev-harness](https://github.com/apixly-ai/jev-harness). Its distribution name is
`apixly-jev-harness`, its Python namespace is `apixly_jev_harness`, and its CLI aliases are
`apixly-jev-harness` and `jev-harness`. The PyPI package named `jev-harness` is an unrelated
project. Use the exact Git installation below. The
[architecture references](architecture.md#references-inspected) identify other projects
without implying endorsement or inherited benchmark results.

<a id="jev-filter-relationship"></a>

## How does Jev Harness relate to Jev Filter?

[Jev Filter](https://github.com/apixly-ai/jev-filter) provides typed semantic selection
and filtering interfaces. Jev Harness builds a bounded observe–choose–execute–verify loop
around registered tools, parameter domains and caller-owned completion checks. It pins
Jev Filter v0.4.1 for its typed-batch inference transport and browser/desktop surfaces;
it does not duplicate that inference implementation. Use a direct filtering interface
when the work is selecting records; use the harness when a task needs multiple bounded
tool decisions with independently observed progress. See [architecture](architecture.md)
and the [adoption sequence](agent-contract.md#adoption-sequence).

<a id="install"></a>

## How do I install the exact v0.1.12 release?

Python 3.10+ and Git are required. Create a virtual environment and install the tagged
repository URL:

```sh
python -m venv .venv
. .venv/bin/activate
pip install 'git+https://github.com/apixly-ai/jev-harness.git@v0.1.12'
jev-harness spec
jev-harness init-task task.py
jev-harness check-task task.py
```

Installation, `spec`, `init-task` and `check-task` make no model calls; downloading packages
still needs network access. Running a task with Jev inference is billable and needs a
caller-supplied credential through `TYPESAFE_API_KEY` or `TYPESAFE_API_KEY_FILE`.
Use `@main` only for active development. Follow the
[first-task instructions](agent-contract.md#install-and-run-your-first-task) before running.

<a id="typed-candidates"></a>

## Can Jev invent commands, selectors or tool arguments?

No. Jev may choose only registered tools and supplied parameter candidates. A candidate
can be a static value or come from a trusted read-only provider derived from the current
observation. `Option(id, description, value)` separates the model-visible description
from the actual bound value; `depends_on` builds a child domain after its parent arguments
are chosen. Singleton domains bind without inference. Model output does not become
executable code, arbitrary text arguments, commands, paths, selectors or coordinates.
Business tools still validate their own conditions. See the
[parameter protocol](agent-contract.md#parameter-protocol).

<a id="suitable-tasks"></a>

## What tasks are suitable for the harness?

Use it for a bounded task with meaningful semantic choices, trusted tools and an observable
completion condition: choosing a prerequisite tool, gathering evidence before a later
action, or preparing a permitted synthetic browser draft. Keep exact arithmetic and fixed
sequences in code. Keep open-ended writing in the primary AI or an explicitly registered
trusted generation tool. The harness has no built-in general form order and candidate
position does not establish priority; the caller supplies scope, preconditions and ordering.
See [next-step tool selection](agent-contract.md#next-step-tool-selection) and the
[documented cases](use-cases.md).

<a id="completion"></a>

## How does Jev Harness know a task is complete?

A `done` result requires the caller's independent verifier to pass against observed state.
A model-only completion returns `needs_review`. Selecting a tool, submitting an action or
receiving a tool result does not itself prove completion. A safe result summary admitted
through `result_context` can advance the next decision without replacing verification.
The terminal packet preserves blocked, missing-context, review and uncertain-execution
outcomes. See [context and results](agent-contract.md#context-and-results) and
[terminal states](agent-contract.md#terminals).

<a id="browser-evidence"></a>

## Is the homepage browser demo a live Jev recording?

The MP4 and GIF are labeled **illustrative screenshot replays**, made from current
headless Camofox captures of the unchanged local synthetic form. They make no new model
calls and are not continuous screen recordings. The separate historical live acceptance
used Jev 1.13.0 with Camofox in v0.1.0, reached the final state in four tool executions,
and independently checked the final DOM text and fields. Early review and authorization
stops remain in the evidence. No real bookings or messages were sent. Read the
[media scope](../web/media/README.md) and [acceptance ledger](../reports/README.md).

<a id="desktop-support"></a>

## Are browser and native desktop tasks supported and verified?

The browser adapter uses a running loopback Camofox service, fresh observed targets,
allowed origins and caller policy for exact click authorization. Native desktop adapters
use pinned macOS Accessibility or Windows UI Automation backends with a named app/window;
the adapter does not support Linux native desktop. Native desktop completion remains
unverified: the Mac acceptance host was locked, and no live Windows acceptance is claimed.
Offline adapter tests do not establish native completion. See [adapters](adapters.md) and
[evidence limits](../reports/README.md).

<a id="billing-and-savings"></a>

## Does Jev Harness guarantee lower cost or faster completion?

No. Real Jev inference is billable. Reports retain whole-operation timing, returned context,
known usage grouped by returned model where available, and unknown usage when evidence is
missing. Missing model identity or interrupted attempts are not counted as zero cost.
Published small development fixtures do not establish universal quality, latency or savings.
Monetary estimates are not invoices and assume no current tariff. Check the
[measurement scope and negative results](../reports/README.md) for each experiment.

Request counts are not invoices. Native Choice's existing telemetry.requests counts
logical packed requests; optional owned_transport records this run's owned SDK-client
attempts and HTTP client-object creation/reuse at terminal finish. Retries can make one
logical request count as three attempts; bad credentials can leave it at zero attempts.
Invalid counters are null, and absent metadata is unknown. Even complete counters do not
prove HTTP delivery, server receipt, inference, billing, TCP connections or other tool
traffic; unknown usage stays unknown. See the
[counter contract](agent-contract.md#transport-counters-owned-by-the-run) and
[A/B scope](../reports/transport-counters-ab.json).

<a id="sandbox-and-idempotency"></a>

## Is the runtime a sandbox, or does it guarantee exactly-once effects?

No. Task scripts are trusted Python; valid configuration still imports them and may cause
top-level effects. Static `check-task` parses and compiles without executing a script, but
passing it does not prove runtime validity. Within one run, the same observation, action
ID and actual bound parameters are blocked before a repeated execution; this is an
execution guard, not a cross-run exactly-once or resume guarantee. The caller's business
tools own identity, authorization, idempotency, transactions and external reconciliation.
Uncertain effects are not automatically retried. See
[static checking](agent-contract.md#static-task-checking),
[execution context](context.md) and [terminals](agent-contract.md#terminals).

An uncertain `DecisionStop` result within the current execution window carries the
available current bound `action_id` for private journal lookup and target reconciliation.
It is not success/count proof, an idempotency key or permission to rerun. Bound arguments
are not added to the terminal, and unknown usage remains unknown. See the
[identity evidence](../reports/execution-identity-ab.json).

<a id="execution-limits"></a>

## What execution and context limits should task authors enforce?

Inference has no result cache, and independent inference concurrency is capped at 30.
The synchronous runtime checks wall-clock budgets between callbacks; each tool must bound
its own I/O and polling. Repeating an identical call against a fixed observation is
unsupported. The default context policy keeps eight recent admitted action results plus
an older action ledger; if admitted context still exceeds the conservative 15,000-character
budget, it returns review rather than silently dropping constraints. Keep raw evidence in
private journals and admit only safe summaries. See [context management](context.md) and
the [synchronous callback contract](agent-contract.md#synchronous-callback-contract).

<a id="request-planning"></a>

## What should an AI do when a selection is not dispatched?

Read `planning` in the current selection's telemetry, and the loop diagnostic's tool or
parameter stage. `request_needs_narrowing` indicates typed input needing narrowing;
`request_needs_context` indicates required context/fields are missing. Unknown planning
statuses use generic `request_planning_review`. Repair the program's candidates/descriptions
or required fields while keeping the goal and safety constraints, rather than blindly retrying.
The native runner was not entered for that selection, but earlier loop calls/effects or
unknown usage may remain. Limits, prompts and model choices are unchanged; provider/HTTP413
failures and generic full-spec validation exceptions are separate. See the
[planning contract](agent-contract.md#request-planning-handoff) and
[offline evidence](../reports/planning-diagnostics-ab.json), without a semantic-quality,
speed or fee claim.
