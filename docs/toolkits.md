# Reusable toolkits and thin task scripts

[简体中文](toolkits.zh-CN.md) · [Task contract](agent-contract.md) · [Use cases](use-cases.md)

Define a goal and compose source tools once. Jev can explore links, files and evidence
whose route and later parameters become known during the run. The task script supplies
scope, completion checks and resource limits; it contains no next-step router.

This page documents the toolkit interfaces and runnable thin scripts. Read the
[acceptance ledger](../reports/README.md) and
[toolkit live report](../reports/toolkit-live-2026-10-11.json) for measured runs and scope.
The examples themselves do not establish general semantic quality, speed or fee advantages.

## Compose the public interfaces

| Interface | Responsibility |
| --- | --- |
| `EvidenceStore` | Retain captured source text in process; expose provenance, small summaries and bounded passage references |
| `WebTools(provider, store)` | Discover current links and sections, follow observed links and read captured sections |
| `HttpProvider` / `CamofoxProvider` | Acquire HTTP text or rendered browser text under caller-defined origin scope |
| `WorkspaceTools(root, store, queries=...)` | Discover, search and read permitted local regular files without executing their source |
| `EvidenceTask` | Compose registered tools with passage reading, labeled evidence and an independently checked saved report |
| `TaskScript(build)` | Build one registered task lazily from validated runtime inputs |
| `ToolkitSession` | Expose the same task for direct reference-based operations or one Jev delegation |

A toolkit has `name`, `observe()` and `install(task)`. Its observation is a compact,
stable projection; observing or offering arguments does not create new source captures.
Acquisition occurs during tool execution, except that `WebTools` construction captures
the entry source when the lazy factory first materializes. Providers expose meaningful
`Option` descriptions and fresh parameter domains through the ordinary `Task` protocol.

## Start with a thin script

[Web research](../examples/research_task.py) and
[workspace investigation](../examples/workspace_task.py) each export
`workflow = TaskScript(build)`. Their source contains no target answer or prescribed
exploration sequence. `build(inputs)` receives runtime configuration and defines the
store, tool pack, evidence labels, output location and caller verifier.

| Input field | Meaning |
| --- | --- |
| `markers` | Required nonempty object mapping quote-category labels to nonempty marker strings |
| `output` | Caller-owned new report path; an existing output is not silently overwritten |
| Web `url`, `allowed_origins` | Permitted entry and allowed origins |
| Workspace `root`, optional `queries` | Permitted source directory and initial literal search terms |

The example verifier checks each requested category against captured quotes using the
input markers. `record_checks` maps each label to a strict boolean passage check; only
categories supported by already read passages are offered. Select the label first, then
its dependent passage. This filters eligible quotes without choosing the next tool.
It illustrates the verification hook; business identity, applicability,
recency and evidence quality belong in the caller's own check. `EvidenceTask` first checks
the actual saved artifact against current records. The verifier then receives **all**
records, including their quoted text, rather than the short decision projection.
`artifact_receipt()` returns the path, existence, match status, record count, digest and
source list so callers can inspect the saved result.

From a repository checkout with the package installed, substitute your permitted test
source and criteria for these illustrative inputs:

```sh
jev-harness check-task examples/research_task.py
jev-harness run examples/research_task.py --goal 'Investigate the requested categories and save sourced quotes' --inputs '{"url":"https://docs.example.org/","allowed_origins":["https://docs.example.org"],"markers":{"requirements":"<source marker>"},"output":"local-results/research.json"}' --max-steps 20 --timeout 120
```

`check-task` is static. A run can acquire sources and Jev inference is billable; credentials
remain in the caller's configured environment. Public paid acceptance used local synthetic
data. Scope and authorization for other datasets remain the caller's responsibility.

## Read evidence progressively

`store.put(text, source, metadata)` returns a capture-specific reference. `describe(ref)`
and `references()` expose source, length, digest, summary and metadata. `read(ref, offset,
limit)` returns a bounded original-text window, up to 1,200 characters. `chunk_options()`
provides passage candidates; `EvidenceTask` also provides passage-page selection.

Whole captured text remains in the store. Jev's observation keeps the last eight source
and record summaries, counts and a `last_read` window of at most 1,200 characters.
Older captures can still be read through references and dynamic passage candidates.
These are in-process captures, not an automatic persistent raw-source archive. The saved
report contains selected records and provenance; a new process cannot resume the old
store or session. The existing loop context budget can still stop an oversized projection.

The shared evidence tools are `read_evidence`, `evidence_page`, `record_evidence` and
`save_report`. Source tool names include `web.open_link`, `web.read_section`,
`files.list`, `files.search` and `files.read`. Jev chooses when to investigate, read,
record or save; code owns reference resolution, source capture and actual execution.

## Discovery and matching

Use `Parameter(..., selection="explore")` for choosing a promising source or planning
the next investigation. An unknown destination need not already prove the goal. Default
`selection="match"` retains the existing matching policy: top probability 0.55 and margin
0.10. `EvidenceTask` tool choice and explore-parameter choice use top probability 0.30
and margin 0.0, retaining other checks. These defaults reflect small development
calibration, not a demonstrated quality improvement or execution authorization.

There is no inference/result cache. Jev selects offered references; the toolkit does not
provide builtin free-text generation. Queries or prose can come from an explicitly
registered trusted generator, validated before entering a candidate pool. Generated
text does not directly become code, commands or selectors.

## Use the same task through MCP

Start a stdio server with the thin script and the same runtime input schema:

```sh
python -m apixly_jev_harness.mcp examples/workspace_task.py --goal 'Investigate source evidence and save quotes' --inputs '{"root":"permitted-corpus","queries":["relevant_identifier"],"markers":{"implementation":"<source marker>"},"output":"local-results/workspace.json"}' --context '{}' --max-steps 20 --timeout 120 --archive local-results/session.jsonl
```

| MCP tool | Operation |
| --- | --- |
| `observe` | Inspect current state, offered tool contracts and argument references |
| `arguments` | Send the current `state_ref` to inspect candidates; parent references resolve dependent child choices |
| `operate` | Send the current `state_ref` and offered parameter IDs to execute one tool |
| `run_task` | Hand the registered task to the Jev loop within the session budget |

For a dependent tool, call `arguments` with the tool name and already selected parent
reference IDs; choose a child from the returned domain. `operate` requires all parameter
IDs from the current offer. Advertised MCP `arguments` and `operate` also require the
fingerprint in the latest `observe.state_ref`. Refresh observations after an operation;
perform operations sequentially in one session. Stale, unoffered or repeated operations
are rejected. Existing Python methods retain optional `state_ref` compatibility, while
MCP clients must send it.

The observation also includes delegation readiness, the current goal, confirmation that
the same tools/verifier are used, and the artifact receipt. Python callers use
`session.delegate()`; the old MCP `delegate` name remains an unadvertised compatibility
alias for `run_task`.

From v0.2.1, `run_task` may be the first session call for a `TaskScript`. Once the loop
materializes the registered task, its `artifact_receipt()` is forwarded in the terminal
`artifact` field when available; callers need not call `observe` first merely to obtain
that receipt. This is delegated functionality, not evidence that an AI naturally chooses
delegation.

Choose direct operation or Jev delegation at the start of the session. Inspection may
precede that choice, but the session cannot switch routes after execution or merge the
two histories. `--direct-only` omits delegation. This is an in-process session, not
cross-process resume; direct-mode caller model costs are outside Jev telemetry. Review
terminal evidence and reconcile uncertain execution rather than retrying it blindly.

## Source-specific boundaries

`HttpProvider` uses GET-only text acquisition with bounded response reads and per-hop
origin checks. It extracts server-rendered HTML/text. For rendered browser content,
replace the research script's provider with:

```python
provider = jev.CamofoxProvider(
    url=inputs["url"], allowed_origins=inputs["allowed_origins"],
    session=inputs["session"], tab=inputs["tab"],
)
```

Run the shared Camofox service headless (`CAMOFOX_INTERACTIVE=off`), retain
`humanize: true`, and use a fixed named session/tab identity. Close only the task-owned
tab; a caller-supplied existing tab remains caller-owned. Browser checks constrain
offered destinations and observed final origins; they are not a network firewall for
redirects or subresources. In-process callers should close their source toolkits when
finished; the MCP server closes its toolkits when the session ends.

Workspace reads are confined to the selected root, reject symlinks and never import or
execute inspected source. They require safe descriptor-relative opens; Windows or other
platforms without that support fail closed. File/search bounds and omissions are explicit.
Neither source toolkit is a Python sandbox; caller-defined scope and independent
completion checks remain essential.
