"""Batch semantic judgment: one typed Jev question over many records in few requests.

inputs: records (JSONL path; each line has id and text), question (what qualifies) and
output (JSON path). The judge tool asks Jev the question for every record, packed into
batched requests, and saves {"ids": matching ids, "review_ids": unclear ids}. verify only
confirms that a report covering every record was saved; check accuracy against your own
labels or spot checks. Edit spec() to change the answer options.
Jev inference is billable (published 2026-10-12: $0.042 per million input tokens,
output free).
"""

import json
from pathlib import Path

import apixly_jev_harness as jev


def spec(question):
    return {
        "questions": {
            "match": {
                "type": "choice",
                "instructions": question,
                "criteria": {
                    "MATCH": "The record satisfies the question.",
                    "OTHER": "The record does not satisfy the question.",
                    "REVIEW": "Unclear from the record text.",
                },
            }
        },
        "filter": {"question": "match", "in": ["MATCH"]},
        "order": {"question": "match", "values": ["MATCH", "REVIEW", "OTHER"]},
    }


def build(inputs):
    question = inputs.get("question")
    if type(question) is not str or not question.strip():
        raise ValueError("question_required")
    source, output = Path(inputs["records"]), Path(inputs["output"])
    records = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            records.append({"id": str(row["id"]), "text": str(row["text"])})
    if not records or len({r["id"] for r in records}) != len(records):
        raise ValueError("unique_records_required")
    saved = {}
    task = jev.Task(
        observe=lambda ctx: {"records": len(records), "saved": bool(saved)},
        verify=lambda ctx, state: state["saved"] is True,
    )

    @task.tool("Judge every record against the question and save the matching ids")
    def judge():
        packet = jev.Engine().decide(records, goal=question, analysis_spec=spec(question))
        report = {
            "ids": packet["selected_ids"],
            "review_ids": packet["review_ids"],
            "judged": len(records),
            "complete": packet["complete"],
        }
        output.write_text(json.dumps(report), encoding="utf-8")
        saved.update(report)
        return {
            "ids": len(report["ids"]),
            "review_ids": len(report["review_ids"]),
            "complete": report["complete"],
        }

    return task


workflow = jev.TaskScript(build)
