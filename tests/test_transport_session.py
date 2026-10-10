import json

import httpx
from jev_context.provider import Client

from jev_harness import AgentLoop, Parameter, Task


def test_loop_reuses_connection_and_never_result_caches(monkeypatch):
    observed = []

    def transport(request):
        body = json.loads(request.content)
        observed.append(body)
        answers = {}
        for key, q in body["questions"].items():
            choices = list(q["criteria"])
            answers[key] = {
                "type": "choice",
                "choice": choices[0],
                "confidence": 1,
                "probabilities": {
                    option: 1.0 if i == 0 else 0.0 for i, option in enumerate(choices)
                },
            }
        return httpx.Response(
            200,
            json={
                "model": "jev-1.13.0",
                "answers": answers,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    client = Client(api_key="synthetic-test-key", transport=httpx.MockTransport(transport))
    monkeypatch.setattr("jev_harness.backend.Client", lambda **kwargs: client)
    state = {"value": 0}
    task = Task(observe=lambda ctx: state.copy(), verify=lambda ctx, seen: seen["value"] == 2)

    @task.tool("Advance", parameters={"amount": Parameter("Amount", [1, 2])})
    def advance(amount):
        state["value"] += amount

    result = AgentLoop().run(task, goal="Reach two")
    assert result["status"] == "done"
    assert len(observed) == 4
    assert client.stats["clients_created"] == 1
    assert client.stats["client_reuses"] == 3
    assert client.closed
