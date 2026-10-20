---
name: jev-harness
description: Optional guide for handing an open goal or recurring batch judgment to a Jev-native loop with reusable toolkits or caller-written tools, fresh argument references and independent artifact checks. First judge whether the work will recur; capture recurring work once as a reusable task script. Keep exact work in code. Choose delegation when its setup and task scope justify it; do not force a route.
---

# Jev Harness

Contract version: 0.2.1. Pin `@v0.2.1` for this release.

Use for open routes with bounded capabilities and observable completion (source research,
read-only repository investigation, browser evidence collection) and for recurring batch
judgment over many records. The primary AI writes
and reviews a trusted task script; Jev selects the next registered tool and its current
parameter references from goal, observation and admitted history. No predefined next-step
router is required. Exact computations and fixed short sequences stay in code; new prose
requires an explicitly registered trusted generator or the primary AI.

## First: will this work recur?

Before choosing a route, decide whether the same kind of work will run again on new data
with the same criteria: daily or weekly operations, a triage queue, a monitor feed, a
recurring report, a new batch every run. Say which way you judged and why. Then:

| Work | Capture it as | Why |
| --- | --- | --- |
| Recurring, per-item judgment over many free-text records (alerts, tickets, logs, reviews) | `init-task --toolkit records`: one typed question per record through `Engine().decide` | Keyword rules break on new wording; Jev judges a batch in seconds |
| Recurring, exact rules suffice (fixed formats, enumerable templates) | A plain script, no Jev | Deterministic, verifiable, no inference cost |
| Recurring multi-step page operation | `SurfaceTask` only after a reference run completes under the unchanged gates | Current Jev confidence often stops multi-step forms at review |
| One-off and small | Do it directly | Setup would cost more than the work |

For recurring work, leave a reusable procedure in the workspace: the task script plus a
short runbook with inputs, criteria, the exact run command, how completion is verified and
the last result and usage. On later runs, rerun the saved script, verify the new result
independently, and update the runbook only when the criteria change. A scheduler can run
the saved script without a primary AI; the primary only needs to review failures.

Evidence (2026-10-12, one Claude primary, synthetic data): on 1,000 free-text alerts the
primary delegated to the records route in 10 of 11 runs, all passing the independent
check. Those runs cost a median $0.27 (its own tokens plus Jev) and took 65 s, against
$0.95 and 147 s for reading every alert. A next-day session reused the saved script on a
new batch. On a template-generated corpus it wrote plain rules instead, which was right.
Published Jev price (2026-10-12): $0.042 per million input tokens, output free.

Start with the machine-readable interface, not this guide:

```sh
jev-harness spec
jev-harness init-task task.py --toolkit workspace
jev-harness check-task task.py
```

`init-task --toolkit records` scaffolds batch judgment over a JSONL file and saves matching
and unclear ids; `--toolkit surface` scaffolds click/select/fill over observed controls,
with `allow(target)` for caller business rules. The evidence templates `workspace`,
`http` and `browser` share `TaskScript(build)` and `EvidenceTask`.
Runtime inputs supply the permitted root/URL, schema labels and markers, and a new output
path. Markers describe evidence categories, never hidden answers or a route. The reusable
packs discover files/links, capture originals and offer bounded read references. The caller
owns the independent completion check. `check-task` is static syntax/export checking.

Submit one authorized run with `--goal`, JSON `--inputs`, `--max-steps`, `--timeout` and a
private `--archive`. `--model` takes a versioned Jev ID (default `jev-1.13.0`); aliases
are rejected. Use caller-approved inference credentials. Explain what goal,
observation and tool/argument candidates Jev will receive before a live call.

Alternatively expose the same task to an AI client:

```sh
jev-harness mcp task.py --goal 'Investigate the permitted sources' --inputs '{...}'
```

The MCP interface offers `observe`, `arguments`, `operate` and `run_task`. The AI can take
either route at the start. `run_task` carries out the current registered goal in one call;
`operate` performs a single registered effect. For `arguments`/`operate`, carry the current
`state_ref` from `observe` and only offered string reference IDs. Resolve parent arguments
before dependent child references. One route per session; no mid-run transfer or durable
resume. No skill installation or route-promoting prompt is needed for MCP.

Parse terminal JSON even on a nonzero exit. Only independent verification plus the saved
artifact proves completion. Keep `needs_context`, `needs_review`, partial failures,
unknown model/usage and `execution_uncertain`. Do not automatically retry uncertain
external effects. Reconcile with the target first.

Scripts are trusted Python, not a sandbox. Tools own permissions, identity, freshness,
idempotency and their own I/O timeouts. Observe/providers remain read-only. Jev never
supplies executable code, selectors, coordinates, arbitrary commands or unvetted text.
No result caching; wall budgets are cooperative. Keep private originals and journals local.
Headless Camofox uses the preserved named session and closes only owned tabs. Workspace
reads refuse symlinks and require secure POSIX directory-fd support.

Full contracts and examples:
- https://apixly-ai.github.io/jev-harness/toolkits.html
- https://apixly-ai.github.io/jev-harness/agent-contract.html
- https://apixly-ai.github.io/jev-harness/context.html
- https://apixly-ai.github.io/jev-harness/evidence.html
- https://github.com/apixly-ai/jev-harness/blob/main/reports/delegation-2026-10-12.md

Choose based on actual whole-task results, setup cost and verified output. A fast delegated
run does not prove an AI will select it naturally or that every task is cheaper/faster.
