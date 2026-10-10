from apixly_jev_harness import AgentLoop, Task


def test_native_choice_selects_tool_and_parameter_combination(monkeypatch):
    completed = []
    task = Task(
        observe=lambda ctx: {"completed": completed.copy()},
        verify=lambda ctx, state: state["completed"] == [[2, "logs"]],
        strategy="joint",
    )

    @task.tool("Inspect the job", parameters={"job_id": [1, 2], "mode": ["status", "logs"]})
    def inspect(job_id, mode):
        completed.append([job_id, mode])
        return {"status": "inspected"}

    def provider(items, **kwargs):
        body = items[0]["request"]
        assert "history" in body["state"]["context"]
        assert len(body["questions"]["target"]["criteria"]) == 9  # 4 calls + 3 exits + NONE/REVIEW
        return {
            "ok": True,
            "usage_complete": True,
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "results": [
                {
                    "id": items[0]["id"],
                    "ok": True,
                    "answers": {
                        "target": {"type": "choice", "choice": "c3", "probabilities": {"c3": 1.0}}
                    },
                }
            ],
        }

    monkeypatch.setattr("apixly_jev_harness.backend.native_run", provider)
    result = AgentLoop().run(task, goal="Inspect job 2 logs")
    assert result["status"] == "done"
    assert completed == [[2, "logs"]]


def test_oversized_context_remains_review_without_provider(monkeypatch):
    def never(*args, **kwargs):
        raise AssertionError("provider must not be called")

    monkeypatch.setattr("apixly_jev_harness.backend.native_run", never)
    task = Task(observe=lambda ctx: {"text": "x" * 50000}, verify=lambda ctx, state: False)

    @task.tool("Read")
    def read():
        raise AssertionError("must not execute")

    result = AgentLoop().run(task, goal="Read")
    assert result["status"] == "needs_review"
    assert result["telemetry"]["requests"] == 0


def test_failed_transport_does_not_claim_requested_model_as_resolved(monkeypatch):
    from apixly_jev_harness import Engine

    def unavailable(items, **kwargs):
        return {
            "ok": False,
            "usage_complete": False,
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "results": [{"id": "choose", "ok": False, "model": "jev-1.13.0"}],
        }

    monkeypatch.setattr("apixly_jev_harness.backend.native_run", unavailable)
    packet = Engine().decide(
        [{"id": "a", "text": "Act"}], goal="Choose", analysis_spec={"mode": "choose"}
    )
    assert packet["telemetry"]["model_resolved"] is None
    assert packet["telemetry"]["models"] == {}
