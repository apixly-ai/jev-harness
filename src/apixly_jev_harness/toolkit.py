"""Compose source toolkits into a thin task with independently checked artifacts."""

import copy
import hashlib
import json
import os
from pathlib import Path

from . import _secure_fs
from .engine import Workflow
from .task import Option, Parameter, Task


def compact_result(packet):
    if not isinstance(packet, dict):
        return {"result_type": type(packet).__name__}
    return {
        key: (
            value[: (1200 if key == "text" else 240)]
            if isinstance(value, str)
            else copy.deepcopy(value)
        )
        for key, value in packet.items()
        if key
        in (
            "ref",
            "source",
            "offset",
            "end",
            "total",
            "text",
            "sha256",
            "count",
            "path",
            "saved",
            "label",
        )
    }


class EvidenceTask(Task):
    def __init__(
        self,
        toolkits,
        *,
        store,
        labels,
        output,
        verify,
        tool_selection_policy=None,
        record_checks=None,
    ):
        from .engine import HOSTED_DEFAULT

        self.tool_selection_policy = copy.deepcopy(
            tool_selection_policy
            if tool_selection_policy is not None
            else {**HOSTED_DEFAULT, "min_top_probability": 0.30, "min_margin": 0.0}
        )
        self.store, self.output = store, Path(output).expanduser().absolute()
        if self.output.exists() or _secure_fs.is_link(self.output):
            raise FileExistsError("report_output_already_exists")
        self.record_checks = dict(record_checks or {})
        if any(not callable(check) for check in self.record_checks.values()):
            raise ValueError("record_checks_must_be_callable")
        self.labels = list(labels)
        if (
            not self.labels
            or any(type(x) is not str or not x for x in self.labels)
            or len(set(self.labels)) != len(self.labels)
            or len(self.labels) > 250
        ):
            raise ValueError("distinct_evidence_labels_required")
        self.toolkits = list(toolkits)
        names = [pack.name for pack in self.toolkits]
        if len(set(names)) != len(names) or any(type(x) is not str or not x for x in names):
            raise ValueError("distinct_toolkit_names_required")
        self.records, self._passages, self._page = [], {}, 0
        self._saved_hash = None
        self._latest_read = None
        self._prepared = False
        self._check = verify
        super().__init__(observe=self._state, verify=self._verify)
        for pack in self.toolkits:
            pack.install(self)
        self.tool(
            "Read a captured source passage to investigate the goal",
            name="read_evidence",
            parameters={
                "passage": Parameter(
                    "Source and character window relevant to the goal",
                    lambda c, s: store.chunk_options(page=self._page),
                    selection="explore",
                )
            },
            result_context=compact_result,
        )(self.read_evidence)
        self.tool(
            "Select another page of captured source passages",
            name="evidence_page",
            available=lambda c, s: store.page_count() > 1,
            parameters={
                "page": Parameter(
                    "Page containing useful source windows",
                    lambda c, s: [
                        Option(str(i), f"Passage page {i + 1}", i)
                        for i in range(store.page_count())
                        if i != self._page
                    ],
                )
            },
            result_context=compact_result,
        )(self.select_page)
        self.tool(
            "Record a read source passage under a requested evidence label",
            name="record_evidence",
            available=lambda c, s: bool(self._label_options()),
            parameters={
                "label": Parameter(
                    "Requested evidence category to support; prefer categories still missing useful evidence",
                    lambda c, s: self._label_options(),
                ),
                "passage": Parameter(
                    "Previously read passage specifically supporting the selected label",
                    lambda c, s, bound: [
                        Option(
                            key,
                            "For category "
                            + str(bound["label"])
                            + ": "
                            + self._passage_description(value),
                            copy.deepcopy(value),
                        )
                        for key, value in self._passages.items()
                        if self._supports_new(bound["label"], value)
                    ],
                    depends_on=("label",),
                ),
            },
            result_context=compact_result,
        )(self.record_evidence)
        self.tool(
            "Save the current evidence report for independent completion checks",
            name="save_report",
            available=lambda c, s: bool(self.records) and not self._artifact_matches(),
            result_context=compact_result,
        )(self.save_report)

    def prepare(self):
        """Run declared source preparations once, without a tool effect or inference."""
        from .callbacks import require_synchronous

        if not self._prepared:
            for pack in self.toolkits:
                callback = getattr(pack, "prepare", None)
                if callback is not None:
                    require_synchronous(callback, "observe")
                    callback()
            self._prepared = True

    def selection_description(self, action):
        """Brief tool contracts; full candidate domains are selected afresh during binding."""
        if self.strategy != "staged":
            return action.description
        description = json.loads(action.description)
        for parameter in description.get("parameters", {}).values():
            choices = parameter.pop("choices", None)
            if choices is not None:
                parameter["candidate_count"] = len(choices)
                parameter["preview"] = [
                    {"id": x["id"], "description": x["description"][:80]} for x in choices[:3]
                ]
                parameter["preview_truncated"] = len(choices) > 3
        return json.dumps(description, ensure_ascii=False)

    def _label_options(self):
        options = []
        for label in self.labels:
            eligible = [
                self._window(p) for p in self._passages.values() if self._supports_new(label, p)
            ]
            if not eligible:
                continue
            sources = list(dict.fromkeys(row["source"] for row in eligible))
            recorded = sum(row["label"] == label for row in self.records)
            description = (
                f"Evidence category: {label}; already recorded: {recorded}; "
                f"record-check eligible read windows: {len(eligible)}; "
                f"source examples: {json.dumps(sources[:3], ensure_ascii=False)}"
            )
            options.append(Option(label, description, label))
        return options

    def _state(self, ctx):
        sources = self.store.references()
        return {
            "toolkits": {pack.name: pack.observe() for pack in self.toolkits},
            "completion": {
                "required_labels": list(self.labels),
                "missing_labels": [
                    x for x in self.labels if not any(r["label"] == x for r in self.records)
                ],
                "report_matches_records": self._artifact_matches(),
                "independent_check_required": True,
            },
            "evidence": {
                "sources": [
                    {
                        **{key: row[key] for key in ("ref", "source", "characters")},
                        "summary": row["summary"][:80],
                    }
                    for row in sources[-8:]
                ],
                "source_count": len(sources),
                "page": self._page,
                "read_passages": list(self._passages),
                "records": [
                    {
                        **{k: copy.deepcopy(v) for k, v in row.items() if k != "text"},
                        "summary": row["text"][:180],
                    }
                    for row in self.records[-8:]
                ],
                "record_count": len(self.records),
                "last_read": copy.deepcopy(self._latest_read),
                "saved": self._artifact_matches(),
            },
        }

    def _artifact_bytes(self):
        return json.dumps(
            {"records": self.records}, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2
        ).encode("utf-8")

    def _artifact_matches(self):
        if self._saved_hash is None or _secure_fs.is_link(self.output):
            return False
        try:
            data = self.output.read_bytes()
            return (
                hashlib.sha256(data).hexdigest() == self._saved_hash
                and data == self._artifact_bytes()
            )
        except OSError:
            return False

    def artifact_receipt(self):
        return {
            "path": str(self.output),
            "exists": self.output.is_file(),
            "matches_records": self._artifact_matches(),
            "record_count": len(self.records),
            "sha256": self._saved_hash,
            "sources": list(dict.fromkeys(row["source"] for row in self.records)),
        }

    def report_snapshot(self, page=0):
        if type(page) is not int or page < 0:
            raise ValueError("nonnegative_report_page_required")
        pages = max(1, (len(self.records) + 3) // 4)
        if page >= pages:
            raise ValueError("report_page_not_available")
        available = self._artifact_matches()
        return {
            "available": available,
            "page": page,
            "pages": pages,
            "record_count": len(self.records),
            "has_more": available and page + 1 < pages,
            "records": copy.deepcopy(self.records[page * 4 : (page + 1) * 4]) if available else [],
            "artifact_sha256": self._saved_hash if available else None,
        }

    def _verify(self, ctx, state):
        if not self._artifact_matches():
            return False
        verification_state = copy.deepcopy(state)
        verification_state["evidence"]["records"] = copy.deepcopy(self.records)
        verification_state["evidence"]["sources"] = self.store.references()[-8:]
        return self._check(ctx, verification_state)

    def _window(self, passage):
        if type(passage) is not dict or set(passage) != {"ref", "offset", "limit"}:
            raise ValueError("evidence_window_required")
        return self.store.read(**passage)

    def _supports(self, label, passage):
        check = self.record_checks.get(label)
        if check is None:
            return not self.record_checks
        passed = check(self._window(passage))
        if type(passed) is not bool:
            raise ValueError("record_check_must_return_bool")
        return passed

    def _supports_new(self, label, passage):
        return (
            self._supports(label, passage)
            and {"label": label, **self._window(passage)} not in self.records
        )

    def _passage_description(self, passage):
        row = self._window(passage)
        return f"{row['source']} | {row['offset']}:{row['end']} | {row['text'][:180]}"

    def read_evidence(self, passage):
        return self._window(passage)

    def select_page(self, page):
        if type(page) is not int or not 0 <= page < self.store.page_count():
            raise ValueError("invalid_evidence_page")
        self._page = page
        return {"count": len(self.store.chunk_options(page=page))}

    def record_evidence(self, passage, label):
        if type(label) is not str or label not in self.labels:
            raise ValueError("unregistered_evidence_label")
        if not self._supports(label, passage):
            raise ValueError("passage_does_not_support_requested_category")
        row = {"label": label, **self._window(passage)}
        if row not in self.records:
            self.records.append(row)
        return row

    def save_report(self):
        data = self._artifact_bytes()
        self.output.parent.mkdir(parents=True, exist_ok=True)
        if self._saved_hash is not None and not self._artifact_matches():
            # Records may have changed since save, but the on-disk owner must still match.
            if (
                _secure_fs.is_link(self.output)
                or not self.output.is_file()
                or hashlib.sha256(self.output.read_bytes()).hexdigest() != self._saved_hash
            ):
                raise ValueError("report_output_changed")
        if self._saved_hash is None:
            fd = _secure_fs.open_private_file(self.output, "x+")
        else:
            if not _secure_fs.WINDOWS and not hasattr(os, "O_NOFOLLOW"):
                raise ValueError("secure_report_update_not_supported")
            fd = _secure_fs.open_private_file(self.output, "r+")
        with os.fdopen(fd, "r+b") as stream:
            # POSIX: regular 0600 file owned by this uid. Windows: regular file whose
            # protected DACL grants only the current user.
            if not _secure_fs.owner_only(stream.fileno()):
                raise ValueError("report_output_owner_changed")
            existing = stream.read()
            if (
                self._saved_hash is not None
                and hashlib.sha256(existing).hexdigest() != self._saved_hash
            ):
                raise ValueError("report_output_changed")
            stream.seek(0)
            stream.truncate()
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        self._saved_hash = hashlib.sha256(data).hexdigest()
        return {"saved": True, "path": str(self.output), "count": len(self.records)}

    def result_context(self, ctx, action, result):
        admitted = super().result_context(ctx, action, result)
        if isinstance(result, dict) and all(x in result for x in ("ref", "offset", "end", "text")):
            window = {
                "ref": result["ref"],
                "offset": result["offset"],
                "limit": min(self.store.read_limit, max(1, result["end"] - result["offset"])),
            }
            captured = self._window(window)
            if any(
                captured[key] != result.get(key)
                for key in ("text", "end", "source", "sha256", "total")
            ):
                raise ValueError("uncaptured_evidence_result")
            key = f"{window['ref']}:{window['offset']}:{window['limit']}"
            self._passages[key] = window
            self._latest_read = captured
        if admitted is not None:
            compact = compact_result(admitted)
            if isinstance(compact.get("text"), str):
                compact["text"] = compact["text"][:240]
            return compact
        return None


class _DelegatedWorkflow(Workflow):
    """Preserve the actual run context without allowing a direct-route transfer."""

    def __init__(self, owner):
        self.owner, self.context, self.checked = owner, None, False

    @property
    def tool_selection_policy(self):
        from .engine import HOSTED_DEFAULT

        return getattr(self.owner.task, "tool_selection_policy", HOSTED_DEFAULT)

    def observe(self, ctx):
        from .callbacks import require_synchronous

        self.context = ctx
        if isinstance(self.owner.task, TaskScript):
            self.owner.task = self.owner.task.materialize(ctx)
        if self.owner.task.strategy != "staged":
            raise ValueError("toolkit_session_requires_staged_task")
        if not self.checked:
            for role in (
                "observe",
                "candidates",
                "execute",
                "verify",
                "authorize",
                "bind",
                "result_context",
                "selection_description",
            ):
                require_synchronous(
                    getattr(self.owner.task, role), role, allow_generator=role == "candidates"
                )
            self.checked = True
        if isinstance(self.owner.task, EvidenceTask):
            self.owner.task.prepare()
        return self.owner.task.observe(ctx)

    def candidates(self, ctx, state):
        return self.owner.task.candidates(ctx, state)

    def selection_description(self, action):
        return self.owner.task.selection_description(action)

    def verify(self, ctx, state):
        return self.owner.task.verify(ctx, state)

    def execute(self, ctx, action):
        return self.owner.task.execute(ctx, action)

    def bind(self, ctx, state, action, choose):
        return self.owner.task.bind(ctx, state, action, choose)

    def authorize(self, ctx, action):
        return self.owner.task.authorize(ctx, action)

    def result_context(self, ctx, action, result):
        return self.owner.task.result_context(ctx, action, result)


class ToolkitSession:
    """Expose the same registered capabilities for direct calls or one Jev delegation.

    Caller-owned task and credentials. This is an in-process session, not durable resume.
    """

    def __init__(
        self,
        task,
        *,
        goal,
        inputs=None,
        context=None,
        max_steps=20,
        timeout_seconds=120,
        archive=None,
    ):
        import time

        from .engine import validate_run_options

        if not isinstance(task, (Task, TaskScript)):
            raise TypeError("registered_task_required")
        self.report_tool_advertised = isinstance(task, (EvidenceTask, TaskScript))
        self.ctx, _ = validate_run_options(
            goal=goal,
            inputs=inputs,
            context=context,
            max_steps=max_steps,
            timeout_seconds=timeout_seconds,
        )
        if isinstance(task, Task) and task.strategy != "staged":
            raise ValueError("toolkit_session_requires_staged_task")
        self.task, self.max_steps = task, max_steps
        self.timeout_seconds, self.archive = timeout_seconds, archive
        self.steps, self._started = 0, time.monotonic()
        self._state, self._offered = None, {}
        self._executed, self._uncertain, self._delegated = set(), False, False
        self.events = []

    def _remaining(self):
        import time

        return self.timeout_seconds - (time.monotonic() - self._started)

    def observe(self):
        if self._remaining() <= 0:
            raise ValueError("session_budget_exceeded")
        from .engine import _fingerprint

        if isinstance(self.task, TaskScript):
            self.task = self.task.materialize(self.ctx)
        if self.task.strategy != "staged":
            raise ValueError("toolkit_session_requires_staged_task")
        self._checkpoint()
        if isinstance(self.task, EvidenceTask):
            self.task.prepare()
        self._state = copy.deepcopy(self.task.observe(self.ctx))
        if self._remaining() <= 0:
            raise ValueError("session_budget_exceeded")
        complete = self.task.verify(self.ctx, copy.deepcopy(self._state))
        if type(complete) is not bool:
            raise ValueError("verifier_must_return_bool")
        if not complete and self._remaining() <= 0:
            raise ValueError("session_budget_exceeded")
        actions = (
            []
            if complete or self._uncertain or self._delegated
            else list(self.task.candidates(self.ctx, copy.deepcopy(self._state)))
        )
        delegation_ready = self.steps == 0 and not self._delegated and not self._uncertain
        if not complete:
            self._checkpoint()
        self._offered = {a.params["tool"]: a for a in actions}
        return {
            "goal": self.ctx.goal,
            "observation": copy.deepcopy(self._state),
            "tools": [json.loads(a.description) for a in actions],
            "remaining_steps": max(0, self.max_steps - self.steps),
            "complete": complete,
            "delegation_available": delegation_ready,
            "delegation": {
                "ready": delegation_ready,
                "goal": self.ctx.goal,
                "uses_same_registered_tools": True,
                "completion_check": "caller independent verifier",
                "artifact": self.task.artifact_receipt()
                if hasattr(self.task, "artifact_receipt")
                else None,
            },
            "state_ref": _fingerprint(self._state),
        }

    def _checkpoint(self, state_ref=None):
        from .engine import _fingerprint

        if self._remaining() <= 0:
            raise ValueError("session_budget_exceeded")
        if state_ref is not None and (
            type(state_ref) is not str or state_ref != _fingerprint(self._state)
        ):
            raise ValueError("stale_client_snapshot")

    def operate(self, tool, parameters, state_ref=None):
        from .engine import _fingerprint

        self._checkpoint(state_ref)
        if self._delegated:
            raise ValueError("direct_unavailable_after_delegation")
        if self._uncertain:
            raise ValueError("execution_uncertain_requires_reconciliation")
        if self.steps >= self.max_steps or self._remaining() <= 0:
            raise ValueError("session_budget_exceeded")
        if type(tool) is not str or tool not in self._offered or type(parameters) is not dict:
            raise ValueError("tool_or_parameters_not_offered")
        state = copy.deepcopy(self.task.observe(self.ctx))
        self._checkpoint()
        if _fingerprint(state) != _fingerprint(self._state):
            raise ValueError("stale_toolkit_state")
        spec = self.task._tools[tool]
        if set(parameters) != set(spec["parameters"]):
            raise ValueError("parameter_references_required")
        values = {}
        for key in spec["order"]:
            identifier = parameters[key]
            if type(identifier) is not str:
                raise ValueError("parameter_reference_required")
            options = self.task._domain(spec["parameters"][key], self.ctx, state, values)
            self._checkpoint()
            matches = [x for x in options if x.id == identifier]
            if len(matches) != 1:
                raise ValueError("parameter_reference_not_offered")
            values[key] = copy.deepcopy(matches[0].value)

        from .engine import Action, _json

        offered = self._offered[tool]
        if not self.task._same_action(offered):
            raise ValueError("action_not_offered")
        action = Action(
            offered.id,
            _json(
                {
                    "tool": tool,
                    "purpose": spec["description"],
                    "selected_parameters": {k: {"id": parameters[k]} for k in parameters},
                }
            ),
            {"tool": tool, "arguments": values},
            offered.irreversible,
        )
        self.task._offered[action.id] = copy.deepcopy(action)
        if action.irreversible and self.task.authorize(self.ctx, action) is not True:
            raise ValueError("tool_requires_authorization")
        if _fingerprint(self.task.observe(self.ctx)) != _fingerprint(state):
            raise ValueError("stale_toolkit_state")
        self._checkpoint()
        call = _fingerprint({"state": state, "action": action.id, "params": action.params})
        if call in self._executed:
            raise ValueError("repeated_action_state")
        self._executed.add(call)
        self.events.append(
            {"route": "direct", "tool": tool, "parameters": copy.deepcopy(parameters)}
        )
        try:
            result = self.task.execute(self.ctx, action)
            self.steps += 1
            self.ctx.step = self.steps
            admitted = self.task.result_context(self.ctx, action, result)
            self.ctx.history.append(
                {
                    "action_id": action.id,
                    "description": action.description,
                    **({"result": admitted} if admitted is not None else {}),
                }
            )
            self.ctx.results.append({"action_id": action.id, "result": result})
            next_state = self.observe()
        except Exception:
            self._uncertain = True
            raise
        return {"result": admitted, **next_state}

    def resolve(self, tool, parameters, state_ref=None):
        self._checkpoint(state_ref)
        from .engine import _fingerprint

        if tool not in self._offered or type(parameters) is not dict:
            raise ValueError("tool_or_parameters_not_offered")
        state = copy.deepcopy(self.task.observe(self.ctx))
        self._checkpoint()
        if _fingerprint(state) != _fingerprint(self._state):
            raise ValueError("stale_toolkit_state")
        spec, values, visible = self.task._tools[tool], {}, {}
        if not set(parameters) <= set(spec["parameters"]):
            raise ValueError("unknown_parameter")
        for key in spec["order"]:
            parameter = spec["parameters"][key]
            if not set(parameter.depends_on) <= set(values):
                if key in parameters:
                    raise ValueError("parent_reference_required")
                continue
            options = self.task._domain(parameter, self.ctx, state, values)
            self._checkpoint()
            if key in parameters:
                matched = [x for x in options if x.id == parameters[key]]
                if type(parameters[key]) is not str or len(matched) != 1:
                    raise ValueError("parameter_reference_not_offered")
                values[key] = copy.deepcopy(matched[0].value)
            else:
                visible[key] = {
                    "description": parameter.description,
                    "choices": [{"id": x.id, "description": x.description} for x in options],
                }
        return {"tool": tool, "parameters": visible}

    def read_report(self, page=0):
        """Read saved verified bytes; execution deadlines do not prevent result retrieval."""
        task = self.task._task if isinstance(self.task, TaskScript) else self.task
        if not isinstance(task, EvidenceTask):
            raise ValueError("evidence_report_not_registered_or_materialized")
        return task.report_snapshot(page)

    def delegate(self):
        from .engine import AgentLoop

        if self.steps:
            raise ValueError("delegation_unavailable_after_direct_actions")
        if self._uncertain or self._delegated:
            raise ValueError("delegation_already_attempted_or_uncertain")
        remaining = self._remaining()
        if self.steps >= self.max_steps or remaining <= 0:
            raise ValueError("session_budget_exceeded")
        self._delegated = True
        self.events.append({"route": "jev"})
        delegated = _DelegatedWorkflow(self)
        result = AgentLoop().run(
            delegated,
            goal=self.ctx.goal,
            inputs=self.ctx.inputs,
            context=self.ctx.facts,
            messages=self.ctx.messages,
            max_steps=self.max_steps - self.steps,
            timeout_seconds=remaining,
            archive=self.archive,
        )
        if delegated.context is not None:
            self.ctx = delegated.context
        self.steps += result["steps"]
        self._uncertain = result["status"] == "execution_uncertain"
        materialized = self.task._task if isinstance(self.task, TaskScript) else self.task
        if hasattr(materialized, "artifact_receipt"):
            result["artifact"] = materialized.artifact_receipt()
        if isinstance(materialized, EvidenceTask):
            result["report"] = materialized.report_snapshot()
        return result


class TaskScript(Workflow):
    """Lazy thin-script factory: receive validated runtime inputs, build once per script."""

    def __init__(self, factory):
        import inspect

        from .callbacks import require_synchronous

        require_synchronous(factory, "task_factory")
        inspect.signature(factory).bind({})
        self.factory, self._task = factory, None

    @property
    def tool_selection_policy(self):
        from .engine import HOSTED_DEFAULT

        return getattr(self._task, "tool_selection_policy", HOSTED_DEFAULT)

    def materialize(self, ctx):
        if self._task is None:
            task = self.factory(copy.deepcopy(ctx.inputs))
            if not isinstance(task, Task):
                raise TypeError("factory_must_return_registered_task")
            from .callbacks import require_synchronous

            require_synchronous(task.selection_description, "selection_description")
            self._task = task
        return self._task

    def observe(self, ctx):
        return self.materialize(ctx).observe(ctx)

    def verify(self, ctx, state):
        return self.materialize(ctx).verify(ctx, state)

    def candidates(self, ctx, state):
        return self.materialize(ctx).candidates(ctx, state)

    def selection_description(self, action):
        if self._task is None:
            raise ValueError("task_not_materialized")
        return self._task.selection_description(action)

    def bind(self, ctx, state, action, choose):
        return self.materialize(ctx).bind(ctx, state, action, choose)

    def execute(self, ctx, action):
        return self.materialize(ctx).execute(ctx, action)

    def authorize(self, ctx, action):
        return self.materialize(ctx).authorize(ctx, action)

    def result_context(self, ctx, action, result):
        return self.materialize(ctx).result_context(ctx, action, result)
