---
name: jev-harness
description: Use a Jev-native agent loop for bounded multi-step tasks when an AI can define trusted tools, meaningful parameter candidates and independent success checks. Generate a task script, run it once and handle terminal evidence; keep exact/fixed work in code and open reasoning in the primary model.
---

# Jev Harness

Contract version: 0.1.3. Install the repository at `@v0.1.3` for a reproducible release;
use `@main` for active development.

Read `jev-harness spec` first. This is a task-script runtime, not a tool interception hook
or a replacement for the primary AI. Prefer it when repeated next-tool/parameter decisions
are semantic and the available action domain and success condition can be bounded.

1. Define the goal, scope, observable success, admitted facts and conversation.
2. `jev-harness init-task task.py` creates a runnable offline scaffold.
3. Register explicit keyword-callable tools with Task.tool; use Parameter descriptions,
   static/dynamic choices and depends_on for related arguments. Use Option to separate
   safe descriptions from private values. Never ask Jev to invent an ID or command.
4. Keep observe/candidate callbacks read-only. Admit safe results via result_context.
5. Test synthetic callback behavior. `check-task` checks syntax/export only, no execution.
6. Tell the user what goal, observation and tool/parameter candidates Jev will receive.
7. Submit one `jev-harness run ...` call. Inference is billable; use caller-approved credentials.
8. Parse terminal JSON even on exit 2. Only independently verified done means completion.

Describe each tool's preconditions and expected effect, and put task priority, order and
exit criteria in the caller's goal and contracts. A next-step tool may gather evidence or
satisfy a prerequisite without completing the entire goal. Candidate position is not
priority; keep business rules in the task instead of the core. The host marks loop
context with decision_stage=tool_selection or parameter_selection. Direct Engine.decide
filtering without that loop marker keeps general candidate-selection semantics. Parameter
binding remains conditional on the selected tool; authorization, independent verification
and exit checks are unchanged.

Admitted non-None tool summaries can advance the next decision when the observation is
unchanged; unadmitted raw results cannot. In one run, the same observation, action ID and
actual bound parameters execute at most once. A repeat stops before execution with
`blocked/repeated_action_state`; history growth is not permission to repeat an effect.
Polling an identical call against a fixed observation is unsupported. Handle it inside
a trusted tool with bounded attempts/time, or expose meaningful observed progress.

When using `verify_state`, supply nonempty text or at least one control condition.
Each expected control field must be observed; a missing field is not observed `null`.
Admitted results and model exit choices never replace independent completion verification.

Do not retry ambiguous external execution. Caller tools own identity, authorization,
idempotency, business transactions and reconciliation. Scripts are trusted Python, not a
sandbox. Protect private journals; recover only necessary evidence for unresolved items.

An unresolved selection may include a host-generated diagnostic with stage
tool_selection or parameter_selection, registered tool_id/parameter for the latter,
allowlisted reason_codes, and automatic_retry=false. Each actual inference entry in
telemetry.calls carries its stage and applicable identifiers. Static domain, policy and
execution errors retain existing terminal reasons. Diagnostics contain no exception
text, response body or bound values, and do not alter status, eligibility or authorization.
Use credential codes to fix host configuration; use uncertainty/selection codes to
review admitted context or candidate meaning. Inspect prior effects before a new run;
unknown errors fall back to generic codes, not an upstream root-cause claim.
The harness does not repeat task calls automatically. The pinned SDK's bounded
429/503/529 retries remain; automatic_retry=false does not promise one network request.
See the contract's Decision diagnostics section for the whitelist. Synthetic offline
HTTP-mock acceptance has zero real model calls, increases terminal bytes, and does not
establish real semantic recovery success.

Use generic browser/desktop adapters only within their platform and target scope. Headless
Camofox must preserve the named session; native desktop needs an unlocked target app.
No declared adapter means no claim of application coverage. Exact selectors/IDs/computation
and fixed sequences need no inference; open-ended generation remains with the primary AI.

See https://apixly-ai.github.io/jev-harness/agent-contract.html and its context/adapters
pages for complete contracts. Tool and parameter domains are recomputed; no result caching.
