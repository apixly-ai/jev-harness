"""Registered tool adapters over pinned Jev Filter browser/desktop surfaces.

The dependency owns observed target resolution and platform safety gates. This
adapter owns tool/parameter contracts and the new generic agent loop.
"""

from urllib.parse import urlsplit

from .engine import DecisionStop
from .task import Option, Parameter, Task


def origin(url):
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}"


class SurfaceTask(Task):
    def __init__(self, surface, *, verify, values=None, allowed_origins=None, authorize=None):
        self.surface, self.snapshot = surface, None
        self.values = dict(values or {})
        self.allowed_origins = set(allowed_origins or [])
        super().__init__(observe=self._observe, verify=verify, authorize=authorize)
        for kind, description in (
            ("click", "Click an observed button, link, checkbox or menu"),
            ("select", "Choose an observed dropdown option"),
        ):
            # Bind the function's default kind in a closure, not a model parameter.
            def register(kind=kind):
                def invoke(target):
                    return self._act(target)

                return invoke

            def targets(kind=kind):
                return lambda ctx, state: self._targets(kind)

            self.tool(
                description,
                irreversible=(kind == "click"),
                name=kind,
                parameters={
                    "target": Parameter(
                        "Observed control required by the earliest unmet instruction. Do not submit until every requested field and toggle is satisfied",
                        targets(),
                    )
                },
            )(register())
        if self.values:
            self.tool(
                "Fill one observed text field using a supplied named value",
                name="fill",
                parameters={
                    "target": Parameter(
                        "Text field matching the supplied value",
                        lambda ctx, state: self._targets("fill"),
                    ),
                    "value": Parameter(
                        "Supplied value appropriate for the selected field",
                        lambda ctx, state, bound: [
                            Option(key, key + ": " + str(value), value)
                            for key, value in self.values.items()
                        ],
                        depends_on=("target",),
                    ),
                },
            )(self._fill)

    def _targets(self, kind):
        result = []
        for action in self.snapshot["actions"]:
            if action["kind"] != kind or action.get("sensitive"):
                continue
            if kind == "click" and action.get("role") in ("textbox", "searchbox"):
                continue
            if (
                kind == "click"
                and action.get("role") == "combobox"
                and any(
                    other["kind"] == "select" and other.get("node") == action.get("node")
                    for other in self.snapshot["actions"]
                )
            ):
                continue
            if kind == "fill" and action.get("value") in self.values.values():
                continue
            if kind == "select" and action.get("value") == action.get("current_value"):
                continue
            result.append(
                Option(
                    action["id"],
                    str(
                        {
                            key: action[key]
                            for key in ("label", "role", "section", "value", "checked", "selected")
                            if key in action
                        }
                    ),
                    action,
                )
            )
        return result

    def _observe(self, ctx):
        snapshot = self.surface.observe()
        if self.allowed_origins and origin(snapshot.get("url", "")) not in self.allowed_origins:
            raise DecisionStop("blocked", "origin_not_allowed")
        self.snapshot = snapshot
        return {
            "title": snapshot.get("title"),
            "url": snapshot.get("url"),
            "text": snapshot.get("text", ""),
            "fingerprint": snapshot["fingerprint"],
            "controls": [
                {
                    key: action[key]
                    for key in ("id", "kind", "label", "role", "value", "checked", "selected")
                    if key in action
                }
                for action in snapshot["actions"]
                if not action.get("sensitive")
            ],
            "omitted_actions": snapshot.get("omitted_actions", 0),
        }

    def _act(self, target, text=None):
        if not self.surface.fresh(self.snapshot, target):
            raise DecisionStop("stale", "surface_target_changed")
        result = self.surface.act(target, self.snapshot, text=text)
        self.surface.settle(target)
        return result

    def _fill(self, target, value):
        return self._act(target, text=value)


def browser_task(
    *,
    url=None,
    tab=None,
    session="general",
    base="http://127.0.0.1:9378",
    values=None,
    verify=None,
    allowed_origins=None,
    authorize=None,
):
    from jev_context.act.browser import CamofoxPage

    if verify is None:
        raise ValueError("independent_verifier_required")
    surface = CamofoxPage(session, tab=tab, url=url, base=base)
    return SurfaceTask(
        surface,
        values=values,
        verify=verify,
        allowed_origins=allowed_origins or ([origin(url)] if url else []),
        authorize=authorize,
    )


def desktop_task(*, window, process=None, values=None, verify=None, authorize=None):
    import sys

    from jev_context.act.desktop import DesktopSurface

    if verify is None:
        raise ValueError("independent_verifier_required")
    if sys.platform == "darwin":
        from jev_context.act.desktop_macos import MacBackend

        backend = MacBackend(window=window, process=process)
    elif sys.platform == "win32":
        from jev_context.act.desktop_windows import WindowsBackend

        backend = WindowsBackend(window=window, process=process)
    else:
        raise RuntimeError("desktop_requires_macos_or_windows")
    return SurfaceTask(DesktopSurface(backend), values=values, verify=verify, authorize=authorize)
