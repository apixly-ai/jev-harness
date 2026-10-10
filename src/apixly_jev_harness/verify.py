"""Exact observable completion checks. No model call or execution authority."""

import copy


def verify_state(*, text=None, controls=()):
    checks = copy.deepcopy(list(controls))
    if text is not None and not isinstance(text, str):
        raise ValueError("verification_text_required")
    for check in checks:
        if not isinstance(check, dict) or not isinstance(check.get("label"), str) or len(check) < 2:
            raise ValueError("control_check_requires_label_and_expected_fields")

    def verify(ctx, state):
        if text is not None and text not in state.get("text", ""):
            return False
        for check in checks:
            matches = [
                control
                for control in state.get("controls", [])
                if control.get("label") == check["label"]
            ]
            if len(matches) != 1 or any(
                matches[0].get(key) != value for key, value in check.items()
            ):
                return False
        return True

    return verify
