"""Deterministic context admission. Full evidence lives in the private journal."""

import copy
from dataclasses import dataclass


@dataclass(frozen=True)
class ContextPolicy:
    recent_steps: int = 8

    def __post_init__(self):
        if type(self.recent_steps) is not int or self.recent_steps < 1:
            raise ValueError("positive_recent_steps_required")

    def build(self, ctx, observation):
        history = copy.deepcopy(ctx.history)
        compacted = max(0, len(history) - self.recent_steps)
        for i in range(compacted):
            history[i] = {
                "action_id": history[i]["action_id"],
                "description": history[i]["description"],
                "result_ref": f"step:{i + 1}",
            }
        return {
            "goal": ctx.goal,
            "facts": copy.deepcopy(ctx.facts),
            "messages": copy.deepcopy(ctx.messages),
            "observation": copy.deepcopy(observation),
            "history": history,
            "compacted_steps": compacted,
            "step": ctx.step,
        }
