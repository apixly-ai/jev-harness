# Context management for Jev decisions

[简体中文](context.zh-CN.md)

Every turn has distinct sections: goal, shared facts, explicitly admitted user/assistant
messages, current observation, action/result history and budgets. Jev receives these
sections plus available tools and parameter descriptions. It does not inherit an AI
host's conversation implicitly.

The host also marks loop inference context with `decision_stage=tool_selection` or
`parameter_selection`. Tool questions concern the next step: evidence gathering and
prerequisite actions may advance the task without completing the entire goal. Caller
goals and tool contracts must supply preconditions, expected effects, priorities and
ordering requirements; candidate position does not supply them. No general UI-form
order is built into the core. A direct `Engine.decide` filter without the loop marker
keeps general candidate-selection semantics. Conditional parameter selection, authorization,
independent verification and exits retain their existing contracts.

An execution may add useful evidence without changing the external observation. A
non-None safe summary admitted through `result_context` is recorded in history and can
advance the next decision in that case. Raw results remain available locally in
`ctx.results` and the journal, but without admission they cannot advance an unchanged
observation. Admission does not establish task completion; the independent verifier
must still pass.

Within one run, the tuple of observation, action ID and actual bound parameters identifies
an invocation. A repeated invocation returns `blocked/repeated_action_state` before
execution. Different bound objects can supply separate evidence even if the summaries
are identical. Fingerprints are execution guards, not result caches. This is not a
cross-run idempotency or exactly-once guarantee.

Repeated polling of the same call against a fixed observation is unsupported. Implement
polling inside a trusted tool with an explicit timeout and attempt bound, or expose
meaningful observed progress. Growing history alone does not authorize another identical
invocation. See the [synthetic offline A/B](../reports/evidence-progress-ab.json); these
checks do not establish live model success or universal performance improvements.

The default ContextPolicy keeps recent admitted results for eight actions and retains
an ordered ledger for all older actions, with `step:N` evidence references. Full evidence
stays in the private JSONL journal and `ctx.results`. Goal, constraints, facts and admitted
messages remain intact. This is deterministic projection, not an inferred or cached summary.

Parameter binding carries selected candidate references/descriptions forward, not private
bound values. The committed action history records the parameters actually chosen, rather
than the entire original candidate menu. Task authors should keep durable task facts in
shared facts or observation and can derive older needed evidence from ctx.results in their
registered tools. The runtime does not automatically decide which business facts are safe
to drop.

The existing loop shared-context budget is 15,000 JSON characters, inclusive: reject
only when `len(json.dumps(context, ensure_ascii=False)) > 15000`, using default
separators. The count includes serialized JSON syntax, spaces and escapes. It counts
Unicode code points in that serialization, not raw field length, UTF-8 bytes or tokens.

The `context_projection` check covers the policy projection plus remaining step/time
budgets. `tool_selection` and `parameter_selection` then measure the shared context with
the host stage marker and selection/binding additions. A projection that fits can still
exceed the limit after these additions. Candidate-record texts, selection questions,
the complete prompt and token/cost budgets are outside this measurement.

Terminals with reason `context_budget_exceeded` can include count-only `context_budget`:
scope `loop_shared_context`, the failing stage, unit `json_characters`, limit and observed
length. This metadata contains no raw context. Returned decision-call telemetry records
`context_characters` and `context_character_limit`, retaining `context_bytes` as the
separate UTF-8 size; exception paths may lack these measurements. The affected oversized
decision normally stops before inference and returns review, rather than silently
truncating constraints. Earlier calls/effects may already exist; usage uncertainty,
effect uncertainty, caller fallbacks and the no-result-cache policy are unchanged.

Direct `Engine.decide` does not receive this loop cap. The pinned upstream's separate
16,000-character full-analysis-spec validation and provider question/state limits remain
in force; fitting this shared-context budget does not prove the complete request fits.
Messages must be admitted user/assistant objects with text content; system policy belongs
in the explicit goal and trusted program. The [offline A/B](../reports/context-budget-ab.json)
checks synthetic admission/measurement with zero real model, network or UI calls. Extra
metadata increases terminal bytes, without establishing semantic quality, speed or savings.

Private journals use exclusive creation, POSIX mode 0600, JSONL append, flush/fsync, and
never overwrite an existing path. They include raw observations, actual arguments and
results. Do not publish them without review. CLI terminal output contains no raw evidence;
trusted scripts must also avoid printing their own raw data.

This design borrows explicit agent state and message projection from pi, lightweight
references/progressive disclosure from Anthropic's context engineering guidance, and
result-to-event history from MellowHarness. It does not claim their full feature sets.
See [architecture references](architecture.md).
