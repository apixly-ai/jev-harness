# The AI-native task contract

The product is a reusable task runtime, not a library of application-specific cases.
An agent should learn one interface and supply its business tools as a short script.

Distribution: **apixly-jev-harness**. Python: `apixly_jev_harness`. CLI aliases:
`apixly-jev-harness` and `jev-harness`. Install from the exact repository URL below;
the existing PyPI jev-harness package is a different project.

## Install and run your first task

Python 3.10+ and Git are required. Installation is offline with respect to model calls;
package downloads still require network access. Pin v0.1.0 for a reproducible release
once that tag is available, or use main for active development.

```sh
python -m venv .venv
. .venv/bin/activate
pip install 'git+https://github.com/apixly-ai/jev-harness.git@main'
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
5. Test callback behavior with synthetic inputs; use `check-task` for syntax/export only.
6. Make one `run` call; parse the terminal packet even on exit 2.
7. Recover unresolved context or reconcile ambiguous execution in the primary agent.

Use the loop for bounded tasks requiring semantic branches. Exact calculations and fixed
sequences stay in code; open-ended writing belongs to the primary agent or an explicit
trusted generation tool. A tool-selection decision is not execution proof or authorization.

## Parameter protocol

Each parameter has a semantic description and a list/tuple of choices, or a read-only
provider `(ctx, observation)` / `(ctx, observation, bound_arguments)`. Choices are JSON
values or `Option(id, description, value)`. Literal values become descriptions; Options
separate a safe model-visible label from the actual value. Do not put credentials in
model-visible labels or observations.

`depends_on=('customer',)` constructs the job domain only after customer is selected.
The graph must be acyclic and name existing parameters. Every returned value belongs to
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

Callbacks `observe` and candidate providers are read-only. `verify` returns strict bool.
`authorize(ctx, action)` returns strict True for the exact irreversible action under prior
caller authorization. Default is no authorization. Execution functions have explicit
keyword-callable signatures; no variadic arguments. Python scripts are trusted, not sandboxed.

## Terminals

`done` requires independent verification. Jev also has typed complete/blocked/missing-context
controls; a model-only completion is `needs_review`. Other statuses are `needs_context`,
`needs_review`, `needs_confirmation`, `blocked`, `stale`, `max_steps`, `budget_exceeded`,
`execution_uncertain`, `failed`. Only done exits 0; all other runtime results exit 2.

Intent is durably recorded before effects. No automatic retry of uncertain execution.
No cross-run resume/exactly-once promise. Business tools own identity, idempotency,
transactions and external reconciliation. Wall budgets are checked between callbacks;
each callback must enforce its I/O timeout. Inference has no result cache.
