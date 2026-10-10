from jev_harness import AgentLoop, Task


def test_native_choice_selects_tool_and_parameter_combination(monkeypatch):
    completed = []
    task = Task(
        observe=lambda ctx: {"completed": completed.copy()},
        verify=lambda ctx, state: state["completed"] == [[2, "logs"]],
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
                    "id": "choose",
                    "ok": True,
                    "answers": {
                        "target": {"type": "choice", "choice": "c3", "probabilities": {"c3": 1.0}}
                    },
                }
            ],
        }

    monkeypatch.setattr("jev_context.pool.run", provider)
    result = AgentLoop().run(task, goal="Inspect job 2 logs")
    assert result["status"] == "done"
    assert completed == [[2, "logs"]]


def test_oversized_context_remains_review_without_provider(monkeypatch):
    def never(*args, **kwargs):
        raise AssertionError("provider must not be called")

    monkeypatch.setattr("jev_context.pool.run", never)
    task = Task(observe=lambda ctx: {"text": "x" * 50000}, verify=lambda ctx, state: False)

    @task.tool("Read")
    def read():
        raise AssertionError("must not execute")

    result = AgentLoop().run(task, goal="Read")
    assert result["status"] == "needs_review"
    assert result["telemetry"]["requests"] == 0
