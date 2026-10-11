import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "benchmarks"))
from open_tasks import fixture


def test_mcp_server_can_initialize_from_an_unrelated_working_directory(tmp_path):
    case = fixture(tmp_path / "sources", "files")
    case["inputs"]["output"] = str(tmp_path / "artifact.json")
    manifest = tmp_path / "actor.json"
    manifest.write_text(json.dumps({"goal": case["goal"], "inputs": case["inputs"]}))
    result = tmp_path / "server.json"
    root = Path(__file__).resolve().parents[1]
    request = (
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05"},
            }
        )
        + "\n"
    )
    r = subprocess.run(
        [
            sys.executable,
            str(root / "benchmarks/open_tasks.py"),
            "--server",
            "--case",
            str(manifest),
            "--result",
            str(result),
        ],
        input=request,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=15,
    )
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["result"]["serverInfo"]["name"] == "jev-toolkit"


def test_independent_verifier_rejects_a_fabricated_source_checksum(tmp_path):
    from open_tasks import independent_check

    case = fixture(tmp_path / "sources", "files")
    case["source_directory"] = str(tmp_path / "sources")
    rows = [
        {
            "label": label,
            "source": name,
            "text": case["inputs"]["requirements"][label],
            "sha256": "fabricated",
            "offset": 0,
            "end": 10,
            "total": 10,
        }
        for label, name in case["expected"].items()
    ]
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"records": rows}))
    assert independent_check(case, report)["passed"] is False


def test_browser_verifier_rejects_valid_length_fabricated_checksum(tmp_path):
    import hashlib

    from open_tasks import independent_check

    case = fixture(tmp_path / "sources", "browser", 1)
    case["source_directory"] = str(tmp_path / "sources")
    text = "Pending dependency: identity-check."
    captures = tmp_path / "captures.json"
    captures.write_text(
        json.dumps(
            {
                "evidence:1": {
                    "source": "http://localhost/maple-dependency.html",
                    "text": text,
                    "sha256": hashlib.sha256(text.encode()).hexdigest(),
                }
            }
        )
    )
    row = {
        "ref": "evidence:1",
        "source": "http://localhost/maple-dependency.html",
        "label": "dependency",
        "text": text,
        "offset": 0,
        "end": len(text),
        "total": len(text),
        "sha256": "a" * 64,
    }
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"records": [row]}))
    result = independent_check(case, report, captures_path=captures)
    assert result["labels"]["dependency"] is False
