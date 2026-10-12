import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "benchmarks"))
from adoption import AuditOutput, legacy_tools


def test_projection_control_keeps_unknown_usage_and_removes_only_new_handoff():
    packet = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "status": "needs_review",
                            "complete": False,
                            "telemetry": {"usage": None},
                            "report": {"available": False},
                        }
                    ),
                }
            ],
            "structuredContent": {"status": "needs_review"},
        },
    }
    output, ledger = io.StringIO(), io.StringIO()
    AuditOutput(output, ledger, legacy=True).write(json.dumps(packet) + "\n")
    r = json.loads(output.getvalue())["result"]
    assert "structuredContent" not in r
    text = json.loads(r["content"][0]["text"])
    assert "report" not in text
    assert text["telemetry"]["usage"] is None
    assert output.getvalue() == ledger.getvalue()


def test_task_presentation_keeps_structured_and_text_packet_intact():
    packet = {
        "id": 1,
        "result": {
            "content": [{"type": "text", "text": '{"complete":true}'}],
            "structuredContent": {"complete": True},
        },
    }
    output, ledger = io.StringIO(), io.StringIO()
    AuditOutput(output, ledger).write(json.dumps(packet) + "\n")
    assert json.loads(output.getvalue()) == packet


def test_control_catalog_is_the_released_four_tool_manifest():
    tools = legacy_tools()
    assert {t["name"] for t in tools} == {"observe", "arguments", "operate", "run_task"}
    assert not any("outputSchema" in t for t in tools)


def test_offline_context_ab_keeps_full_domains_and_originals():
    from handoff_context import run

    result = run()
    old, new = result["legacy_projection"], result["compact_projection"]
    assert new["context_bytes"] < old["context_bytes"]
    assert new["candidate_bytes"] < old["candidate_bytes"]
    assert new["request_planned"] is True
    assert result["originals_and_sha256_preserved"] is True
    assert result["full_parameter_domain_count"] > result["preview_domain_count"] == 3
    assert result["adoption_measured"] is False
    assert old["actual_model_usage"]["requests"] == new["actual_model_usage"]["requests"] == 0
