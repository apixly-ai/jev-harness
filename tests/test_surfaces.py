from jev_harness.engine import Context
from jev_harness.surfaces import SurfaceTask


class FakeSurface:
    def __init__(self):
        self.actions = [{"id": "e1", "kind": "click", "label": "Apply", "role": "button"}]
        self.calls = []

    def observe(self):
        return {"fingerprint": "stable", "url": "http://127.0.0.1:8000/", "actions": self.actions}

    def fresh(self, state, target):
        return True

    def act(self, target, state, text=None):
        self.calls.append(target["id"])
        return {"executed": True}

    def settle(self, target):
        pass


def test_observed_control_domain_and_effect_gate():
    surface = FakeSurface()
    task = SurfaceTask(surface, verify=lambda ctx, state: False)
    ctx = Context("Apply", {}, {})
    state = task.observe(ctx)
    offered = task.candidates(ctx, state)
    assert offered[0].irreversible is True
    bound = task.bind(ctx, state, offered[0], lambda *args: None)
    assert bound.params["arguments"]["target"]["id"] == "e1"
    assert task.authorize(ctx, bound) is False
