import io
import json

import pytest

from apixly_jev_harness import Option, Parameter, Task, TaskScript, ToolkitSession
from apixly_jev_harness.evidence import EvidenceStore
from apixly_jev_harness.mcp import describe_tools, serve
from apixly_jev_harness.toolkit import EvidenceTask

CALLBACK_HINTS = {
    "readOnlyHint": False,
    "destructiveHint": True,
    "idempotentHint": False,
    "openWorldHint": True,
}
REPORT_HINTS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}


def rpc(client, requests, **options):
    output = io.StringIO()
    serve(
        client,
        source=io.StringIO("".join(json.dumps(row) + "\n" for row in requests)),
        destination=output,
        **options,
    )
    return [json.loads(row) for row in output.getvalue().splitlines()]


@pytest.mark.parametrize(
    ("lazy", "delegate", "execution_name", "count"),
    [
        (False, False, "run_task", 3),
        (False, True, "run_task", 4),
        (True, False, "run_task", 4),
        (True, True, "run_task", 5),
        (True, True, "collect_evidence", 5),
    ],
)
def test_mcp_lists_explicit_hints_without_materializing_task(lazy, delegate, execution_name, count):
    calls = []

    def build(inputs):
        calls.append("factory")
        return Task(observe=lambda ctx: {}, verify=lambda ctx, seen: False)

    task = TaskScript(build) if lazy else build({})
    calls.clear()
    client = ToolkitSession(task, goal="Inspect the synthetic task")
    response = rpc(
        client,
        [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}],
        allow_delegate=delegate,
        execution_name=execution_name,
    )[0]
    listed = response["result"]["tools"]
    assert len(listed) == count
    assert calls == [] and client.steps == 0 and client.events == []
    for tool in listed:
        expected = REPORT_HINTS if tool["name"] == "read_report" else CALLBACK_HINTS
        assert tool["annotations"] == expected
        assert all(type(value) is bool for value in tool["annotations"].values())


def test_observe_and_arguments_hints_preserve_side_effectful_callback_contract():
    calls = []

    def observe(ctx):
        calls.append("observe")
        return {"ready": True}

    def choices(ctx, seen):
        calls.append("domain")
        return [Option("first", "First synthetic value", 1)]

    task = Task(observe=observe, verify=lambda ctx, seen: False)

    @task.tool("Read a supplied value", parameters={"value": Parameter("Value", choices)})
    def inspect(value):
        calls.append("execute")
        return value

    client = ToolkitSession(task, goal="Inspect synthetic callbacks")
    first = client.observe()
    client.observe()
    before = len(calls)
    client.resolve("inspect", {}, state_ref=first["state_ref"])
    client.resolve("inspect", {}, state_ref=first["state_ref"])
    assert calls[before:] == ["observe", "domain", "observe", "domain"]
    assert calls.count("observe") == 4 and "execute" not in calls
    hints = {tool["name"]: tool["annotations"] for tool in describe_tools(client)}
    assert hints["observe"] == CALLBACK_HINTS
    assert hints["arguments"] == CALLBACK_HINTS


def test_read_report_hints_describe_repeatable_local_reads_without_callbacks(tmp_path):
    store = EvidenceStore()
    ref = store.put("Synthetic captured evidence.", "synthetic-source")
    task = EvidenceTask(
        [],
        store=store,
        labels=["evidence"],
        output=tmp_path / "report.json",
        verify=lambda ctx, seen: pytest.fail("report reads must not call the verifier"),
    )
    task.record_evidence({"ref": ref, "offset": 0, "limit": 1200}, "evidence")
    task.save_report()
    saved = task.output.read_bytes()
    client = ToolkitSession(task, goal="Read a saved synthetic report")
    replies = rpc(
        client,
        [
            {"id": 1, "method": "tools/list"},
            *[
                {
                    "id": identifier,
                    "method": "tools/call",
                    "params": {"name": "read_report", "arguments": {"page": 0}},
                }
                for identifier in (2, 3)
            ],
        ],
    )
    report = next(tool for tool in replies[0]["result"]["tools"] if tool["name"] == "read_report")
    assert report["annotations"] == REPORT_HINTS
    first = replies[1]["result"]["structuredContent"]
    assert first == replies[2]["result"]["structuredContent"]
    assert (
        first["available"] is True and first["records"][0]["text"] == "Synthetic captured evidence."
    )
    assert task.output.read_bytes() == saved and client.events == [] and client.steps == 0
