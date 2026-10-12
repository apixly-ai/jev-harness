"""Offline same-runtime projection A/B using the real Jev request planner.

Synthetic sources stay local. This measures request admission and retained source/parameter
contracts, not model accuracy, task latency or adoption. Neither arm dispatches inference.
"""

import argparse
import copy
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def run():
    from adoption_cases import fixture
    from jev_filter import analysis
    from open_tasks import build

    from apixly_jev_harness import Context, ContextPolicy
    from apixly_jev_harness.engine import EXIT_CONTROLS

    with tempfile.TemporaryDirectory(prefix="jev-handoff-context-") as directory:
        root = Path(directory)
        case = fixture(root / "sources", "medium", 0)
        case["inputs"]["output"] = str(root / "report.json")
        task = build(case["inputs"])
        pack = task.toolkits[0]
        try:
            pack.search_files("retry")
            ctx = Context(case["goal"], case["inputs"], {})
            # A fixed legitimate source-read history; both arms retain the same entries.
            for row in task.store.references():
                text = task.store.read(row["ref"])
                ctx.history.append(
                    {
                        "action_id": "read_evidence",
                        "description": json.dumps(
                            {
                                "tool": "read_evidence",
                                "purpose": "Read captured source",
                                "selected_parameters": {
                                    "passage": {
                                        "id": row["ref"] + ":0",
                                        "description": row["source"] + " | characters 0:1200",
                                    }
                                },
                            }
                        ),
                        "result": {
                            **{
                                k: text[k]
                                for k in ("ref", "source", "offset", "end", "total", "sha256")
                            },
                            "text": text["text"][:240],
                        },
                    }
                )
            current = task.observe(ctx)
            legacy = copy.deepcopy(current)
            legacy["evidence"]["sources"] = task.store.references()[-8:]
            legacy["toolkits"]["files"]["captured"] = task.store.references()[-8:]
            actions = task.candidates(ctx, current)
            output = {}
            for arm, state, describe in (
                ("legacy_projection", legacy, lambda a: a.description),
                ("compact_projection", current, task.selection_description),
            ):
                context = {**ContextPolicy().build(ctx, state), "decision_stage": "tool_selection"}
                records = [
                    {"id": a.id, "text": describe(a), "source_id": a.id, "source": {}}
                    for a in actions
                ]
                records += [
                    {"id": k, "text": v, "source_id": k, "source": {}}
                    for k, v in EXIT_CONTROLS.items()
                ]
                start = time.perf_counter()
                plan = analysis.plan(
                    records,
                    "Choose the next tool for the supplied investigation",
                    {"mode": "choose", "context": context},
                )
                output[arm] = {
                    "planning_seconds": time.perf_counter() - start,
                    "request_planned": bool(plan["items"]),
                    "deferred_statuses": sorted(set(plan["deferred"].values())),
                    "context_bytes": len(json.dumps(context, ensure_ascii=False).encode()),
                    "candidate_bytes": len(json.dumps(records, ensure_ascii=False).encode()),
                    "actual_model_usage": {
                        "requests": 0,
                        "usage_complete": True,
                        "usage": {"input_tokens": 0, "output_tokens": 0},
                    },
                }
            complete_source_cards = task.store.references()
            authentic = all(
                task.store._get(row["ref"])["sha256"]
                == hashlib.sha256(task.store._get(row["ref"])["text"].encode()).hexdigest()
                and task.store._get(row["ref"])["text"]
                == (root / "sources" / row["metadata"]["path"]).read_text(encoding="utf-8")
                for row in complete_source_cards
            )
            search = task._tools["files.search"]["parameters"]["query"]
            domain = task._domain(search, ctx, current, {})
            output.update(
                {
                    "mode": "offline_request_planning_ab",
                    "comparison_scope": "same runtime, old observation/candidate projection reconstructed vs compact projection",
                    "source_files_captured": len(complete_source_cards),
                    "originals_and_sha256_preserved": authentic,
                    "full_parameter_domain_count": len(domain),
                    "preview_domain_count": len(
                        json.loads(
                            task.selection_description(
                                next(a for a in actions if a.id == "files.search")
                            )
                        )["parameters"]["query"]["preview"]
                    ),
                    "source_text_returned_publicly": False,
                    "model_accuracy_measured": False,
                    "task_latency_measured": False,
                    "adoption_measured": False,
                }
            )
            return output
        finally:
            pack.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    packet = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(packet))


if __name__ == "__main__":
    main()
