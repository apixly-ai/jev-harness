# The AI-native task contract

The product is a reusable task runtime, not a library of application-specific cases.
An agent should learn one interface and supply its business tools as a short script.

Distribution: **apixly-jev-harness**. Python: `apixly_jev_harness`. CLI aliases:
`apixly-jev-harness` and `jev-harness`. Install from the exact repository URL below;
the existing PyPI jev-harness package is a different project.

## Install and run your first task

Python 3.10+ and Git are required. Installation is offline with respect to model calls;
package downloads still require network access. Pin v0.1.4 for a reproducible release;
use `@main` instead for active development.

```sh
python -m venv .venv
. .venv/bin/activate
pip install 'git+https://github.com/apixly-ai/jev-harness.git@v0.1.4'
jev-harness spec
jev-harness skill
jev-harness init-task task.py
jev-harness check-task task.py
# Billable: point to a private credential file configured locally.
export TYPESAFE_API_KEY_FILE='/path/to/private/test-key'
jev-harness run task.py --goal 'Reach the requested target' --inputs '{"target":3}'
```

TYPESAFE_API_KEY may be provided by the host's secret mechanism instead. Never commit
keys or put their contents in the task script/CLI arguments. init-task creates a
self-contained synthetic counter; no browser/desktop dependency is required for the
first task. Inspect status/complete/archive/telemetry in the returned JSON. Use the
[adapters](adapters.md) only when your task actually needs those surfaces.

## Adoption sequence

1. Read `jev-harness spec` (offline JSON).
2. Define the goal, scope, admitted facts/messages and observable success condition.
3. Generate `jev-harness init-task task.py` and register tools with explicit signatures.
4. Describe parameters with `Parameter(description, choices, depends_on=...)`.
5. Test callback behavior with synthetic inputs; use `check-task` for static checks only.
6. Make one `run` call; parse the terminal packet even on exit 2.
7. Recover unresolved context or reconcile ambiguous execution in the primary agent.

Use the loop for bounded tasks requiring semantic branches. Exact calculations and fixed
sequences stay in code; open-ended writing belongs to the primary agent or an explicit
trusted generation tool. A tool-selection decision is not execution proof or authorization.

## Static task checking

`check-task` reads UTF-8 source, parses an AST and compiles it without execution. It never
executes the checked script, loads its module, imports its dependencies or calls callbacks.
The static export check accepts an explicit top-level `workflow` assignment (`Assign` or
`AnnAssign` with a value). For example, `workflow = expression` and
`workflow: object = expression` declare an assignment; `workflow: object` alone does not
bind a value. Dynamic or conditional exports are not inferred.

A passing result retains the JSON code `syntax_and_export_ok`. It means only that this
Python interpreter can compile the source and the AST declares that assignment. It does
not prove the `workflow` type, successful imports, reachable execution, tool signatures,
candidate providers or effects. Other Python versions and warning policies may differ.

Uncompilable source returns `invalid_python` with `line`; non-UTF-8 source returns
`source_not_utf8`. Parsing/compilation warnings, when present, are exposed only as
`source_warnings: [{"code": "python_source_warning", "line": N}]`; warning text and
source excerpts are not exported or printed to stderr. These diagnostics do not execute
or semantically validate a task.

The [static-check A/B](../reports/static-check-ab.json) uses fixed offline script samples
without executing any checked script, with zero model or real UI calls. It tests static
admission and safe diagnostics, not runtime task success.

## Next-step tool selection

The loop asks Jev to select one offered tool or exit for the **next step**, using the
entire goal as context. An evidence-gathering or prerequisite action can be suitable even
when it cannot finish the goal in one call. State each tool's preconditions and expected
effect, and supply task order, priority and exit criteria in the caller's goal and tool
contracts. Candidate list position is not priority. The core imposes no general UI-form
ordering rules; business sequencing belongs to the task author.

The host adds `decision_stage=tool_selection` or `parameter_selection` to loop decision
context. This marker scopes the question; it does not provide permission or success proof.
Direct `Engine.decide` filtering without the loop marker retains general candidate-selection
semantics. Parameters still choose a value conditional on the selected tool's next call.
Authorization, independent completion verification and typed exit checks remain unchanged.

The [offline](../reports/tool-choice-offline-ab.json) and
[live](../reports/tool-choice-live-ab.json) tool-choice A/B reports concern six development
synthetic single-decision cases with normal and reversed candidate order. The probe stops
before intent. This scope cannot establish full-task, browser or desktop completion, or
general quality/cost benefits; measured outcomes and usage belong in the reports.

## Parameter protocol

Each parameter has a semantic description and a list/tuple of choices, or a read-only
provider `(ctx, observation)` / `(ctx, observation, bound_arguments)`. Choices are JSON
values or `Option(id, description, value)`. Literal values become descriptions; Options
separate a safe model-visible label from the actual value. Do not put credentials in
model-visible labels or observations.

`depends_on=('customer',)` constructs the job domain only after customer is selected.
The graph must be acyclic and name existing parameters. Describe a parameter for the
selected tool’s next invocation; do not ask one value to finish the whole task.
Compute exact arithmetic and fixed values in code; singleton domains need no inference. Every returned value belongs to
an actually supplied candidate. No model-generated tool names, paths, scripts or selectors.
No arbitrary free-text argument generation or general JSON Schema validation in v0.1.
Tools must validate business conditions themselves.

Default staged binding selects a tool, then each parameter in dependency order. Singleton
domains bind without inference. It avoids Cartesian explosion. Explicit `strategy='joint'`
supports small complete-call catalogs for controlled comparisons. Maximum 250 tools/calls
and 253 choices per parameter. Empty child domains request context, not guessed values.

## Context and results

`Context`: goal, inputs, facts, messages, step, results, history. Inputs/bound values are
not automatically sent to Jev. `result_context(result)` explicitly admits a safe JSON
summary; full results remain local. Source observations/results are evidence, not instructions.

A newly admitted non-None summary can advance the loop when the observation is unchanged.
Unadmitted raw results alone cannot advance that state. Within one run, repeating the
same observation, action ID and actual bound parameters stops before execution with
`blocked` and reason `repeated_action_state`. Different bound objects remain distinct
calls even if their result summaries happen to be equal. This guard stores invocation
fingerprints, not cached results; it does not promise cross-run exactly-once execution.

The loop does not poll an identical call against a fixed observation. Put such polling
inside a tool that enforces its own timeout and attempt limit, or provide meaningful
observed progress. Do not add artificial counters to disguise repeated external effects.

Callbacks `observe` and candidate providers are read-only. `verify` returns strict bool.
`authorize(ctx, action)` returns strict True for the exact irreversible action under prior
caller authorization. Default is no authorization. Execution functions have explicit
keyword-callable signatures; no variadic arguments. Python scripts are trusted, not sandboxed.

`verify_state(text=..., controls=...)` requires nonempty text or at least one control
condition. Every expected control field must be present in the observed control; a missing
field does not establish an observed `null`. Completion still requires the independent
verifier, even when admitted results allowed further tool decisions.

## Terminals

`done` requires independent verification. Jev also has typed complete/blocked/missing-context
controls; a model-only completion is `needs_review`. Other statuses are `needs_context`,
`needs_review`, `needs_confirmation`, `blocked`, `stale`, `max_steps`, `budget_exceeded`,
`execution_uncertain`, `failed`. Only done exits 0; all other runtime results exit 2.

Intent is durably recorded before effects. No automatic retry of uncertain execution.
No cross-run resume/exactly-once promise. Business tools own identity, idempotency,
transactions and external reconciliation. Wall budgets are checked between callbacks;
each callback must enforce its I/O timeout. Inference has no result cache.

## Decision diagnostics

A terminal packet may include an optional host-generated `diagnostic` for an unresolved
tool or parameter inference call. It does not change the terminal status, execution
eligibility or authorization. For example:

```json
{
  "status": "needs_review",
  "complete": false,
  "diagnostic": {
    "stage": "parameter_selection",
    "tool_id": "inspect_record",
    "parameter": "record",
    "reason_codes": ["model_review"],
    "automatic_retry": false
  }
}
```

`stage` is `tool_selection` or `parameter_selection`. The parameter stage includes
`tool_id` and `parameter` from the registered binding context. Each actual inference
entry in `telemetry.calls` carries the same stage and applicable identifiers. Singleton
bindings do not make inference calls. Static domain, policy and execution failures
continue to use their existing terminal reasons; diagnostics cover selection calls only.

`reason_codes` admits only these stable codes:

- Provider: `credentials_missing`, `credentials_invalid`, `credential_file_permissions`,
  `client_closed`, `response_too_large`, `transport_failed_usage_unknown`,
  `response_invalid_usage_unknown`, `retry_exhausted`, `provider_unavailable`, and
  `http_NNN_body_suppressed` for HTTP status codes 100–599.
- Selection: `below_min_top_probability`, `below_min_margin`, `below_min_confidence`,
  `selected_option_not_top`, `model_review`, `no_matching_candidate`, `invalid_selection`,
  `unresolved_selection`, `decision_failed`.

Diagnostics never export exception text, response bodies or bound parameter values.
Unknown errors fall back to generic codes; a code is a handoff signal, not a diagnosis
of the upstream root cause. Missing/unknown usage remains unknown.

The primary agent can repair local credential configuration for a credential code,
or inspect admitted context and narrow ambiguous candidates for a selection code.
Inspect the status and journal before submitting a new task: a failed later decision
does not undo earlier effects. Reconcile uncertain execution rather than retrying it.
`automatic_retry: false` means the harness does not automatically repeat task calls;
the pinned SDK's existing bounded 429/503/529 retries are unchanged. It does not promise
one network request or automatic recovery.

The [decision-diagnostics A/B](../reports/decision-diagnostics-ab.json) uses synthetic
offline HTTP mocks and zero real model calls. It checks safe codes and stage metadata.
The extra metadata increases terminal bytes, unknown errors lose detail, and no real
semantic recovery success rate has been established.
