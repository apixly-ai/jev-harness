# Open goals, dynamic tools and Jev delegation

[简体中文](open-goals.zh-CN.md) · [Task contract](agent-contract.md) · [Cases](use-cases.md)

**Give a goal. The primary AI writes a task script. Jev chooses the next step from fresh
observations until there is a verifiable result or an explicit stop.**

The route, future pages, resources and parameter values may be unknown at startup.
Bounds apply to tool permissions, allowed scope and resources. They do not require a
complete predefined route or an enumeration of every future candidate. Each execution
still uses registered tools and values supplied by the program from the current state.

## What the core demonstrates

| Stage | Owner | What the user can inspect |
| --- | --- | --- |
| Define the task | Primary AI | Goal, tool signatures/descriptions, observation and completion checks, scope and budgets |
| Discover the state | Program | Pages, files, resources, evidence and parameter candidates appearing during this step |
| Choose the next step | Jev | Tool choice, argument choices and dependencies, continuation, review or stop |
| Execute and feed back | Program | Actual outcome, refreshed state, admitted summaries and history |
| Deliver | Independent checks and primary AI | An artifact with checkable sources or target state, plus unresolved items |

The script supplies capabilities rather than a task-specific router choosing every next
step for Jev. Exact calculations, parsing and checks belong in code. Preconditions can
control currently available capabilities; facts that the task must discover should not
be required as startup `required_context`.

`Parameter.choices(ctx, observation, bound_arguments)` already supplies fresh domains.
`depends_on` acquires child choices after selecting a parent. A static complete pool is
not required.

The same registered task can be exposed through MCP without a separate next-step router.
Discovery presents a goal-bound execution description, the independent check and budgets;
`initialize.instructions` explains direct `operate` calls and whole-task Jev execution.
The execution tool advertises an `outputSchema` and returns JSON text plus
`structuredContent`, including optional artifact receipts and original report quotes.
Callers may name the execution action with `--execution-name`; its title and description
continue to identify Jev Harness. This makes the capability legible to an AI without
requiring a skill rule that dictates its route.

Workspace first observation performs bounded metadata preparation, not source-body reads.
Captured sources share one compact evidence index with 80-character summaries; full
SHA-256, metadata and the 240-character `store.describe()` summary remain local. After
saving, `read_report` reads up to four original quotes per page only while the artifact
matches current records. Readback is available after either route and performs no task
effects or inference. See [toolkit contracts](toolkits.md) for binding and pagination.

## Flagship: explore an unfamiliar multi-page source

**Example goal:** “Starting from this unfamiliar catalog, find three self-hosted tools
that meet the supplied requirements and save a comparison with checkable sources.”

The primary AI supplies general capabilities: open discovered sources, read pages,
select observed filters, collect evidence and save a source dossier. Jev chooses which
source to inspect, when to filter, which branch deserves exploration and when the
evidence is ready for independent checking. New links and filter dependencies appear
only after opening a page.

The initial artifact is structured: tool name, source URL, original excerpt, requirement match and
acquisition reference. New search wording or a final article requires an explicit trusted
generation tool or the primary AI; the current Jev choice interface does not generate
arbitrary text. Generated results must be validated before becoming candidate data;
generator model usage and timing are recorded separately.

### How acceptance demonstrates exploration

1. Freeze one script and general tool set; change only the entry point and task inputs.
2. Use two different successful routes and one missing-source variant. The task cannot
   read hidden fixture routes or answer oracles.
3. Offer new target references only after observing them. Candidates come from the state,
   not a fixture answer table.
4. Retain Jev inputs, tool/parameter descriptions, original selections, actual trajectories
   and independent checks.
5. Independently check three distinct tools and source support for every supplied
   requirement. Recheck saved URLs and excerpts; missing support stays unresolved.
   Page text saying “done” is not proof.
6. Keep wrong turns, review, blocking, unknown usage and whole-operation timing. Do not
   retry uncertain execution automatically.

**Status: design and acceptance requirements; no completed live Jev/Camofox evidence for
this case yet.** The historical fixed-form result remains in the
[evidence ledger](../reports/README.md) and does not substitute for this acceptance.

## Two cases reusing the same mechanism

### Repository exploration and diagnosis

Give a repository and a recorded failure such as duplicate task submission. General tools
list allowed files, read them, search symbols, inspect existing test/log artifacts and
save evidence. Jev chooses files, symbols and evidence as new relationships and outcomes appear. An explicit generator may
help formulate hypotheses or explanations; generated text never becomes a shell command.

Independent checks verify cited files/revisions and report evidence. The initial case reads
source and existing artifacts, then saves a diagnosis outside the source tree. It does
not execute repository programs. **Status: design; complete live acceptance is pending.**

### Diagnose tasks through a controlled API

Give a failing task entry ID and a diagnosis goal. General tools list resources, read
status/logs, discover dependencies, page through evidence, choose approved checks and
save a diagnosis. Response data reveals resource IDs and dependencies. Jev decides the
inspection order and arguments. Initial acceptance uses a read-only synthetic environment.

Independent readback distinguishes supported causes, hypotheses needing review and
unavailable evidence. **Status: design; complete live acceptance is pending.**

## Mechanisms to prioritize now

| Priority | Current state | What the next acceptance must demonstrate |
| --- | --- | --- |
| General browser discovery | Dynamic surface targets exist; the default adapter still has form-order bias and does not cover every browsing primitive | Unknown branches, same-label links, filter dependencies and long content, with origin and freshness checks intact |
| Evidence references and bounded reads | Shared source index, bounded passage reads and verified report pagination are available; full captures remain local | Large-result exploration and older evidence readback without losing goals or constraints; keep context-budget stops visible |
| Exploration recovery before execution | Empty dependent domains currently stop with needs_context; authors can express preconditions using available | Explicitly recoverable missing facts return to Jev to choose discovery, with decision limits; uncertain execution is never retried |

The table separates current interfaces from further acceptance requirements. Adapters and cases
validate the general mechanism; application-specific behavior stays outside the core.
Cross-process recovery and native desktop completion remain unproven.

## What the homepage should show

Lead with benefits and use: an open goal, AI-authored tools, fresh context for Jev and a
checkable artifact. Task examples show newly discovered candidates, changing routes and
accumulating evidence. Keep incomplete or unknown status banners out of the homepage;
technical contracts and the evidence ledger retain precise acceptance scope and negative results.

Link adoption to [the spec/task contract](agent-contract.md) and acceptance to
[raw evidence](../reports/README.md). Fix/test counts do not replace open-task acceptance.
Whole-task cost or speed gains require a comparison with the primary AI calling tools
directly; that comparison has not been established.
