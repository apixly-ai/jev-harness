from apixly_jev_harness.engine import Context
from apixly_jev_harness.surfaces import SurfaceTask


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


def test_caller_filter_narrows_offered_controls_with_row_context():
    surface = FakeSurface()
    surface.actions = [
        {
            "id": "p1",
            "kind": "click",
            "label": "Include A",
            "role": "checkbox",
            "row": "A | active",
        },
        {
            "id": "p2",
            "kind": "click",
            "label": "Include B",
            "role": "checkbox",
            "row": "B | archived",
        },
    ]
    seen = []

    def allow(target):
        seen.append(target)
        return "active" in target.get("row", "")

    task = SurfaceTask(surface, verify=lambda ctx, state: False, allow=allow)
    ctx = Context("Include active rows", {}, {})
    state = task.observe(ctx)
    assert state["controls"][0]["row"] == "A | active"
    bound = task.bind(ctx, state, task.candidates(ctx, state)[0], lambda *args: None)
    assert bound.params["arguments"]["target"]["id"] == "p1"
    assert "node" not in seen[0] and seen[0]["row"] == "A | active"


def test_caller_filter_must_be_synchronous_and_return_bool():
    import pytest

    async def asynchronous(target):
        return True

    with pytest.raises(Exception):
        SurfaceTask(FakeSurface(), verify=lambda ctx, state: False, allow=asynchronous)
    with pytest.raises(ValueError, match="target_filter_callable_required"):
        SurfaceTask(FakeSurface(), verify=lambda ctx, state: False, allow="yes")
    task = SurfaceTask(FakeSurface(), verify=lambda ctx, state: False, allow=lambda t: 1)
    ctx = Context("Apply", {}, {})
    with pytest.raises(ValueError, match="target_filter_must_return_bool"):
        task.candidates(ctx, task.observe(ctx))
