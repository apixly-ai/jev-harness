import json

import pytest
from platform_support import broaden_access, make_symlink, owner_only, restore_owner_only

from apixly_jev_harness.evidence import EvidenceStore
from apixly_jev_harness.toolkit import EvidenceTask


def test_store_retains_large_source_and_reads_tail_without_admitting_full_text():
    store = EvidenceStore()
    original = "preface " * 3000 + "tail: offline mode is supported"
    ref = store.put(original, "https://example.org/manual", {"title": "Manual"})
    summary = store.describe(ref)
    assert summary["characters"] == len(original)
    assert len(json.dumps(summary)) < 1000
    assert summary["metadata"]["title"] == "Manual"
    tail = store.read(ref, len(original) - 50, 50)
    assert tail["text"] == original[-50:]
    assert tail["end"] == tail["total"]
    assert tail["source"] == "https://example.org/manual"


def test_evidence_identity_is_capture_specific_and_invalid_reads_fail():
    store = EvidenceStore()
    a = store.put("same evidence", "source")
    b = store.put("same evidence", "source")
    assert a != b  # Retaining captures is not inference/result caching.
    assert len(store.references()) == 2
    for offset, limit in [(True, 1), (-1, 1), (0, True), (0, 0), (0, 1201)]:
        with pytest.raises(ValueError):
            store.read(a, offset, limit)
    with pytest.raises(ValueError):
        store.read("invented-ref")


def test_thin_task_installs_toolkit_and_saved_report_is_independently_checked(tmp_path):
    store = EvidenceStore()
    ref = store.put("Requirement: offline use supported.", "allowed-source")

    class Pack:
        name = "local"

        def observe(self):
            return {"ready": True}

        def install(self, task):
            @task.tool("Inspect the source", name="local.inspect", result_context=lambda x: x)
            def inspect():
                return {"source": "allowed-source"}

    output = tmp_path / "report.json"
    task = EvidenceTask(
        [Pack()],
        store=store,
        labels=["offline"],
        output=output,
        verify=lambda ctx, seen: any(
            row["label"] == "offline" and "offline use supported" in row["text"]
            for row in seen["evidence"]["records"]
        ),
    )
    assert "local.inspect" in task.describe()
    assert task.observe(None)["toolkits"]["local"]["ready"] is True
    assert task.verify(None, task.observe(None)) is False
    task.record_evidence({"ref": ref, "offset": 0, "limit": 1200}, "offline")
    assert task.verify(None, task.observe(None)) is False  # Needs a saved real artifact.
    task.save_report()
    assert task.verify(None, task.observe(None)) is True
    report = json.loads(output.read_text())
    assert report["records"][0]["source"] == "allowed-source"
    report["records"][0]["text"] = "fabricated"
    output.write_text(json.dumps(report), encoding="utf-8", newline="\n")
    assert task.verify(None, task.observe(None)) is False


def test_unknown_or_modified_passage_cannot_become_record(tmp_path):
    store = EvidenceStore()
    ref = store.put("original", "source")
    task = EvidenceTask(
        [], store=store, labels=["claim"], output=tmp_path / "out.json", verify=lambda c, s: True
    )
    with pytest.raises(ValueError):
        task.record_evidence({"ref": "fake", "offset": 0, "limit": 1200}, "claim")
    with pytest.raises(ValueError):
        task.record_evidence({"ref": ref, "offset": 0, "limit": 1200}, "unregistered-label")
    with pytest.raises(ValueError):
        task.record_evidence({"ref": ref, "offset": 0, "limit": 1200, "text": "fake"}, "claim")


def test_toolkit_names_and_output_ownership_are_explicit(tmp_path):
    class Pack:
        name = "same"

        def observe(self):
            return {}

        def install(self, task):
            pass

    with pytest.raises(ValueError):
        EvidenceTask(
            [Pack(), Pack()],
            store=EvidenceStore(),
            labels=["x"],
            output=tmp_path / "x",
            verify=lambda c, s: False,
        )
    occupied = tmp_path / "existing.json"
    occupied.write_text("owner document", encoding="utf-8", newline="\n")
    with pytest.raises(FileExistsError):
        EvidenceTask(
            [], store=EvidenceStore(), labels=["x"], output=occupied, verify=lambda c, s: False
        )


def test_actual_read_window_reaches_model_context_and_source_identity_is_checked(tmp_path):
    from apixly_jev_harness import Action
    from apixly_jev_harness.toolkit import compact_result

    store = EvidenceStore()
    text = "x" * 600 + "The required evidence is here."
    ref = store.put(text, "real-source")
    task = EvidenceTask(
        [], store=store, labels=["claim"], output=tmp_path / "x.json", verify=lambda c, s: False
    )
    row = store.read(ref)
    action = Action(
        "read_evidence",
        "read",
        {
            "tool": "read_evidence",
            "arguments": {"passage": {"ref": ref, "offset": 0, "limit": 1200}},
        },
    )
    task.candidates(None, task.observe(None))
    task.result_context(None, action, row)
    assert "required evidence is here" in task.observe(None)["evidence"]["last_read"]["text"]
    assert compact_result(row)["text"] == text
    with pytest.raises(ValueError, match="uncaptured"):
        task.result_context(None, action, {**row, "source": "invented-source"})


def test_many_captured_records_keep_observation_bounded_but_verifier_sees_all(tmp_path):
    store = EvidenceStore()
    checked = []
    task = EvidenceTask(
        [],
        store=store,
        labels=["fact"],
        output=tmp_path / "all.json",
        verify=lambda c, s: checked.append(len(s["evidence"]["records"])) or True,
    )
    for i in range(12):
        ref = store.put("source body " * 100, str(i))
        task.record_evidence({"ref": ref, "offset": 0, "limit": 1200}, "fact")
    assert len(json.dumps(task.observe(None))) < 10000
    task.save_report()
    assert task.verify(None, task.observe(None)) is True
    assert checked == [12]


def test_workspace_search_keeps_source_index_compact_without_discarding_originals(tmp_path):
    from apixly_jev_harness.workspace import WorkspaceTools

    root = tmp_path / "source"
    root.mkdir()
    bodies = {}
    for i in range(8):
        bodies[f"source-{i}.txt"] = f"needle record {i} with source provenance\n" * 10
        (root / f"source-{i}.txt").write_text(
            bodies[f"source-{i}.txt"], encoding="utf-8", newline="\n"
        )
    store = EvidenceStore()
    pack = WorkspaceTools(root, store, queries=["needle"])
    task = EvidenceTask(
        [pack],
        store=store,
        labels=["fact"],
        output=tmp_path / "report.json",
        verify=lambda c, s: False,
    )
    packet = pack.search_files("needle")
    seen = task.observe(None)
    assert len(json.dumps(seen)) < 3600
    assert len(seen["evidence"]["sources"]) == 8
    assert all(len(row["summary"]) <= 80 for row in seen["evidence"]["sources"])
    assert all("summary" not in row for row in seen["toolkits"]["files"]["captured"])
    for match in packet["matches"]:
        ref = match["ref"]
        assert store.read(ref)["text"] == bodies[match["path"]]
        assert store.describe(ref)["metadata"]["match_lines"] == list(range(1, 11))
        assert len(store.describe(ref)["summary"]) == 240
    pack.close()


def test_compact_model_sources_preserve_full_source_cards_for_independent_verifier(tmp_path):
    store = EvidenceStore()
    ref = store.put("Source fact with full provenance", "source:one", {"version": "current"})
    checked = []
    task = EvidenceTask(
        [],
        store=store,
        labels=["fact"],
        output=tmp_path / "report.json",
        verify=lambda c, s: checked.append(s["evidence"]["sources"]) or True,
    )
    task.record_evidence({"ref": ref, "offset": 0, "limit": 1200}, "fact")
    task.save_report()
    assert "metadata" not in task.observe(None)["evidence"]["sources"][0]
    assert task.verify(None, task.observe(None)) is True
    assert checked == [[store.describe(ref)]]


def test_evidence_tool_selection_briefs_keep_all_fresh_parameter_choices(tmp_path):
    from apixly_jev_harness import Context, Option, Parameter

    store = EvidenceStore()
    task = EvidenceTask(
        [],
        store=store,
        labels=["fact"],
        output=tmp_path / "report.json",
        verify=lambda c, s: False,
    )
    values = [Option(str(i), f"Source term {i}: " + "description " * 30, i) for i in range(80)]

    @task.tool(
        "Inspect a supplied source",
        parameters={"value": Parameter("Relevant source", lambda c, s: values)},
    )
    def inspect(value):
        return value

    ctx = Context("Investigate", {}, {})
    action = next(x for x in task.candidates(ctx, task.observe(ctx)) if x.id == "inspect")
    full = json.loads(action.description)
    assert len(full["parameters"]["value"]["choices"]) == 80
    brief = json.loads(task.selection_description(action))
    domain = brief["parameters"]["value"]
    assert domain["candidate_count"] == 80
    assert len(domain["preview"]) == 3 and domain["preview_truncated"] is True
    assert len(task.selection_description(action)) < 800
    selected_domains = []

    def choose(records, *args):
        selected_domains.append(records)
        return {"ok": True, "complete": True, "selected_ids": ["79"]}

    bound = task.bind(ctx, task.observe(ctx), action, choose)
    assert len(selected_domains[0]) == 80
    assert bound.params["arguments"] == {"value": 79}
    assert task.execute(ctx, bound) == 79


def test_record_category_choices_explain_eligibility_without_prescribing_order(tmp_path):
    from apixly_jev_harness import Context

    store = EvidenceStore()
    ref = store.put("Source category marker and original evidence", "source:current")
    task = EvidenceTask(
        [],
        store=store,
        labels=["fact", "other"],
        output=tmp_path / "report.json",
        verify=lambda c, s: False,
        record_checks={"fact": lambda row: "marker" in row["text"], "other": lambda row: False},
    )
    passage = {"ref": ref, "offset": 0, "limit": 1200}
    row = task.read_evidence(passage)
    # Invoke the existing admission using a normally bound action.
    ctx = Context("Save source fact", {}, {})
    offered = next(x for x in task.candidates(ctx, task.observe(ctx)) if x.id == "read_evidence")
    bound = task.bind(ctx, task.observe(ctx), offered, lambda *a: None)
    task.result_context(ctx, bound, row)
    options = task._domain(
        task._tools["record_evidence"]["parameters"]["label"], ctx, task.observe(ctx), {}
    )
    assert [x.id for x in options] == ["fact"]
    assert "source:current" in options[0].description
    assert "already recorded: 0" in options[0].description
    assert "eligible read windows: 1" in options[0].description
    task.record_evidence(passage, "fact")
    extra = store.put("Another marker with additional evidence", "source:second")
    more = {"ref": extra, "offset": 0, "limit": 1200}
    task.result_context(ctx, bound, task.read_evidence(more))
    later = task._domain(
        task._tools["record_evidence"]["parameters"]["label"], ctx, task.observe(ctx), {}
    )
    assert "already recorded: 1" in later[0].description
    assert later[0].value == "fact"


def test_record_tool_is_not_offered_when_all_eligible_read_windows_are_already_recorded(tmp_path):
    from apixly_jev_harness import Context

    store = EvidenceStore()
    ref = store.put("Fact", "source:current")
    task = EvidenceTask(
        [], store=store, labels=["fact"], output=tmp_path / "r.json", verify=lambda c, s: False
    )
    ctx = Context("Collect source evidence", {}, {})
    state = task.observe(ctx)
    read = next(x for x in task.candidates(ctx, state) if x.id == "read_evidence")
    bound = task.bind(ctx, state, read, lambda *a: None)
    task.result_context(ctx, bound, task.execute(ctx, bound))
    assert "record_evidence" in {x.id for x in task.candidates(ctx, task.observe(ctx))}
    task.record_evidence({"ref": ref, "offset": 0, "limit": 4}, "fact")
    assert "record_evidence" not in {x.id for x in task.candidates(ctx, task.observe(ctx))}


def test_exploration_policy_is_explicit_and_only_applies_to_tool_stage(tmp_path, monkeypatch):
    from apixly_jev_harness import AgentLoop

    store = EvidenceStore()
    store.put("read me", "source")
    task = EvidenceTask(
        [], store=store, labels=["fact"], output=tmp_path / "out.json", verify=lambda c, s: False
    )
    policies = []

    def decide(records, **kwargs):
        policies.append(kwargs["analysis_spec"]["uncertainty"])
        return {
            "ok": True,
            "complete": True,
            "selected_ids": ["__loop_blocked"],
            "review_ids": [],
            "telemetry": {
                "requests": 0,
                "usage_complete": True,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        }

    engine = AgentLoop()
    monkeypatch.setattr(engine, "decide", decide)
    result = engine.run(task, goal="Explore source")
    assert result["status"] == "blocked"
    assert policies[0]["min_top_probability"] == 0.30
    assert policies[0]["min_margin"] == 0


def test_exploration_parameters_are_distinct_from_fact_matching():
    from apixly_jev_harness import Parameter

    assert Parameter("Inspect an unknown source", [1], selection="explore").selection == "explore"
    with pytest.raises(ValueError):
        Parameter("Unknown policy", [1], selection="force")
    assert Parameter("Select a field value", [1]).selection == "match"


def test_record_binds_requested_category_before_choosing_its_source(tmp_path):
    from apixly_jev_harness import Action

    store = EvidenceStore()
    task = EvidenceTask(
        [],
        store=store,
        labels=["cause", "proof"],
        output=tmp_path / "report.json",
        verify=lambda c, s: False,
    )
    for text in ["Cause source", "Recorded proof source"]:
        ref = store.put(text, text)
        packet = store.read(ref)
        task.result_context(
            None, Action("read_evidence", "read", {"tool": "read_evidence"}), packet
        )
    actions = task.candidates(None, task.observe(None))
    chosen = next(x for x in actions if x.id == "record_evidence")
    seen = []

    def choose(records, goal, extra):
        seen.append(extra)
        if extra["parameter"] == "label":
            identifier = "proof"
        else:
            assert extra["bound_references"]["label"]["id"] == "proof"
            identifier = next(x["id"] for x in records if "Recorded proof" in x["text"])
        return {"ok": True, "complete": True, "selected_ids": [identifier]}

    bound = task.bind(None, task.observe(None), chosen, choose)
    assert seen[0]["parameter"] == "label"
    assert bound.params["arguments"]["label"] == "proof"


def test_record_tool_requires_a_read_passage_before_binding_children(tmp_path):
    store = EvidenceStore()
    store.put("Entry with links", "entry")
    task = EvidenceTask(
        [], store=store, labels=["fact"], output=tmp_path / "out.json", verify=lambda c, s: False
    )
    assert "record_evidence" not in {x.id for x in task.candidates(None, task.observe(None))}


def test_report_rewrite_refuses_changed_permissions_and_symlink(tmp_path):
    store = EvidenceStore()
    ref = store.put("fact", "source")
    task = EvidenceTask(
        [], store=store, labels=["fact"], output=tmp_path / "report.json", verify=lambda c, s: False
    )
    task.record_evidence({"ref": ref, "offset": 0, "limit": 1200}, "fact")
    task.save_report()
    assert owner_only(task.output)
    broaden_access(task.output)
    with pytest.raises(ValueError):
        task.save_report()
    restore_owner_only(task.output)
    task.output.unlink()
    other = tmp_path / "owner.txt"
    other.write_text("owner data", encoding="utf-8", newline="\n")
    make_symlink(task.output, other)
    with pytest.raises((ValueError, OSError)):
        task.save_report()
    assert other.read_text() == "owner data"


def test_schema_checks_offer_only_categories_with_read_support(tmp_path):
    from apixly_jev_harness import Action

    store = EvidenceStore()
    task = EvidenceTask(
        [],
        store=store,
        labels=["deployment", "storage"],
        output=tmp_path / "r.json",
        verify=lambda c, s: False,
        record_checks={
            "deployment": lambda row: "Deployment method:" in row["text"],
            "storage": lambda row: "Persistent datastore:" in row["text"],
        },
    )
    ref = store.put("Deployment method: unknown until read.", "manual")
    task.result_context(
        None, Action("read_evidence", "read", {"tool": "read_evidence"}), store.read(ref)
    )
    actions = task.candidates(None, task.observe(None))
    record = next(x for x in actions if x.id == "record_evidence")
    assert [x["id"] for x in json.loads(record.description)["parameters"]["label"]["choices"]] == [
        "deployment"
    ]
    resolved = task._domain(
        task._tools["record_evidence"]["parameters"]["passage"],
        None,
        task.observe(None),
        {"label": "storage"},
    )
    assert resolved == []


def test_observation_exposes_required_labels_and_saved_artifact_contract(tmp_path):
    from apixly_jev_harness import Context, EvidenceStore, EvidenceTask

    task = EvidenceTask(
        [],
        store=EvidenceStore(),
        labels=["cause", "proof"],
        output=tmp_path / "report.json",
        verify=lambda c, s: False,
    )
    state = task.observe(Context(goal="Investigate", inputs={}, facts={}, messages=[]))
    assert state["completion"]["required_labels"] == ["cause", "proof"]
    assert state["completion"]["missing_labels"] == ["cause", "proof"]
    assert state["completion"]["report_matches_records"] is False
    assert state["completion"]["independent_check_required"] is True


def test_saved_report_handoff_contains_original_quotes_and_rejects_changed_disk(tmp_path):
    from apixly_jev_harness import EvidenceStore, EvidenceTask

    store = EvidenceStore()
    ref = store.put("Recorded observation: current version is 2.3.", source="source:current")
    task = EvidenceTask(
        [],
        store=store,
        labels=["version"],
        output=tmp_path / "report.json",
        verify=lambda c, s: True,
    )
    task.record_evidence({"ref": ref, "offset": 0, "limit": 1200}, "version")
    task.save_report()
    packet = task.report_snapshot()
    assert packet["available"] is True
    assert packet["records"][0]["text"] == "Recorded observation: current version is 2.3."
    assert packet["records"][0]["sha256"] == store.describe(ref)["sha256"]
    task.output.write_text("{}", encoding="utf-8", newline="\n")
    assert task.report_snapshot()["available"] is False
    assert task.report_snapshot()["records"] == []
