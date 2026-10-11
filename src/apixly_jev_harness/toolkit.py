"""Compose source toolkits into a thin task with independently checked artifacts."""

import copy
import hashlib
import json
import os
import stat
from pathlib import Path

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
        if self.output.exists() or self.output.is_symlink():
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
            available=lambda c, s: bool(self._passages),
            parameters={
                "label": Parameter(
                    "Requested evidence category to support; prefer categories still missing useful evidence",
                    lambda c, s: [
                        Option(x, x, x)
                        for x in self.labels
                        if not self.record_checks
                        or any(self._supports(x, p) for p in self._passages.values())
                    ],
                    selection="explore",
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
                        if self._supports(bound["label"], value)
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

    def _state(self, ctx):
        return {
            "toolkits": {pack.name: pack.observe() for pack in self.toolkits},
            "evidence": {
                "sources": self.store.references()[-8:],
                "source_count": len(self.store.references()),
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
        if self._saved_hash is None or self.output.is_symlink():
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

    def _verify(self, ctx, state):
        if not self._artifact_matches():
            return False
        verification_state = copy.deepcopy(state)
        verification_state["evidence"]["records"] = copy.deepcopy(self.records)
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
                self.output.is_symlink()
                or not self.output.is_file()
                or hashlib.sha256(self.output.read_bytes()).hexdigest() != self._saved_hash
            ):
                raise ValueError("report_output_changed")
        if self._saved_hash is None:
            fd = os.open(self.output, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        else:
            if not hasattr(os, "O_NOFOLLOW"):
                raise ValueError("secure_report_update_not_supported")
            fd = os.open(self.output, os.O_RDWR | os.O_NOFOLLOW)
        with os.fdopen(fd, "r+b") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600
                or (hasattr(os, "getuid") and info.st_uid != os.getuid())
            ):
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

        self._state = copy.deepcopy(self.task.observe(self.ctx))
        if isinstance(self.task, TaskScript):
            self.task = self.task.materialize(self.ctx)
        if self.task.strategy != "staged":
            raise ValueError("toolkit_session_requires_staged_task")
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
        result = AgentLoop().run(
            self.task,
            goal=self.ctx.goal,
            inputs=self.ctx.inputs,
            context=self.ctx.facts,
            messages=self.ctx.messages,
            max_steps=self.max_steps - self.steps,
            timeout_seconds=remaining,
            archive=self.archive,
        )
        self.steps += result["steps"]
        self._uncertain = result["status"] == "execution_uncertain"
        if hasattr(self.task, "artifact_receipt"):
            result["artifact"] = self.task.artifact_receipt()
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
            self._task = task
        return self._task

    def observe(self, ctx):
        return self.materialize(ctx).observe(ctx)

    def verify(self, ctx, state):
        return self.materialize(ctx).verify(ctx, state)

    def candidates(self, ctx, state):
        return self.materialize(ctx).candidates(ctx, state)

    def bind(self, ctx, state, action, choose):
        return self.materialize(ctx).bind(ctx, state, action, choose)

    def execute(self, ctx, action):
        return self.materialize(ctx).execute(ctx, action)

    def authorize(self, ctx, action):
        return self.materialize(ctx).authorize(ctx, action)

    def result_context(self, ctx, action, result):
        return self.materialize(ctx).result_context(ctx, action, result)
