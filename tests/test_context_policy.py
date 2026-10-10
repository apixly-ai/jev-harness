from jev_harness import Context, ContextPolicy


def test_compaction_keeps_action_ledger_and_references():
    ctx = Context("Goal", {}, {"constraint": "keep"})
    ctx.messages = [{"role": "user", "content": "Keep the requested scope"}]
    ctx.history = [
        {"action_id": str(i), "description": "Act", "result": {"large": "x" * 1000}}
        for i in range(10)
    ]
    packet = ContextPolicy(recent_steps=2).build(ctx, {"value": 10})
    assert len(packet["history"]) == 10
    assert packet["compacted_steps"] == 8
    assert packet["history"][0]["result_ref"] == "step:1"
    assert packet["history"][-1]["result"]["large"]
    assert packet["messages"] == ctx.messages
    assert packet["facts"] == ctx.facts
