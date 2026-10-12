"""Thin form/control task: Jev picks observed click/select/fill targets toward the goal.

inputs: url, optional allowed_origins and named session, values (named fill texts) and
done_text (text shown once the result is saved). Fill types only supplied named values.
Clicks are irreversible and run only when authorize allows them; labels matching DENY are
never clicked. Put business rules in allow: it narrows which observed controls Jev may
pick. Replace open_surface to bind another observed surface, and replace verify
with an independent check of the saved result when your system has one: page text is
weaker evidence. Pass a narrower goal per run to repeat the task for several objects.
Jev inference is billable (published 2026-10-12: $0.042 per million input tokens,
output free).
"""

import re

from apixly_jev_harness import TaskScript
from apixly_jev_harness.surfaces import SurfaceTask, origin

DENY = r"\b(send|delete|remove|activate|publish|pay|purchase)\b"


def open_surface(inputs):
    """Observed surface with observe/fresh/act/settle; default is a named Camofox tab."""
    from jev_context.act.browser import CamofoxPage

    return CamofoxPage(
        inputs.get("session", "general"),
        url=inputs["url"],
        base=inputs.get("camofox_url", "http://127.0.0.1:9378"),
    )


def allow(target):
    """Offer a control to Jev? target has label, role, section, row, value, checked, selected."""
    return True


def build(inputs):
    values, done_text = inputs.get("values") or {}, inputs.get("done_text")
    if type(values) is not dict or any(type(v) is not str for v in values.values()):
        raise ValueError("named_string_values_required")
    if type(done_text) is not str or not done_text.strip():
        raise ValueError("verify_contract_required")
    deny = re.compile(inputs.get("deny", DENY), re.I)
    surface = open_surface(inputs)

    def authorize(ctx, action):
        target = action.params["arguments"].get("target")
        return (
            isinstance(target, dict)
            and target.get("kind") == "click"
            and not deny.search(str(target.get("label", "")))
        )

    def verify(ctx, observation):
        return done_text in observation["text"]

    return SurfaceTask(
        surface,
        values=values,
        allowed_origins=inputs.get("allowed_origins") or [origin(inputs["url"])],
        verify=verify,
        authorize=authorize,
        allow=allow,
    )


workflow = TaskScript(build)
