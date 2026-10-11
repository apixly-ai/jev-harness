---
name: jev-harness
description: Optional guide for handing an open goal to a Jev-native loop with reusable source toolkits or caller-written tools, fresh argument references and independent artifact checks. Keep exact work in code. Choose delegation when its setup and task scope justify it; do not force a route.
---

# Jev Harness

Contract version: 0.2.0. Pin `@v0.2.0` for this release.

Use for open routes with bounded capabilities and observable completion: source research,
read-only repository investigation, or browser evidence collection. The primary AI writes
and reviews a trusted task script; Jev selects the next registered tool and its current
parameter references from goal, observation and admitted history. No predefined next-step
router is required. Exact computations and fixed short sequences stay in code; new prose
requires an explicitly registered trusted generator or the primary AI.

Start with the machine-readable interface, not this guide:

```sh
jev-harness spec
jev-harness init-task task.py --toolkit workspace
jev-harness check-task task.py
```

`workspace`, `http` and `browser` templates share `TaskScript(build)` and `EvidenceTask`.
Runtime inputs supply the permitted root/URL, schema labels and markers, and a new output
path. Markers describe evidence categories, never hidden answers or a route. The reusable
packs discover files/links, capture originals and offer bounded read references. The caller
owns the independent completion check. `check-task` is static syntax/export checking.

Submit one authorized run with `--goal`, JSON `--inputs`, `--max-steps`, `--timeout` and a
private `--archive`. Use caller-approved inference credentials. Explain what goal,
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

Choose based on actual whole-task results, setup cost and verified output. A fast delegated
run does not prove an AI will select it naturally or that every task is cheaper/faster.
