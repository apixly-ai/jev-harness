"""Exact observable completion checks. No model call or execution authority."""

import copy
import math


def _key_tag(value):
    kind = type(value)
    if kind is type(None):
        return ("null", None)
    if kind is bool:
        return ("boolean", value)
    if kind is int or kind is float and math.isfinite(value):
        return ("number", value)
    if kind is str:
        return ("string", value)
    return None


def _equal(left, right):
    left_kind, right_kind = type(left), type(right)
    if left_kind is bool or right_kind is bool:
        return left_kind is right_kind and left is right
    if (left_kind is int or left_kind is float) and (right_kind is int or right_kind is float):
        return (
            (left_kind is int or math.isfinite(left))
            and (right_kind is int or math.isfinite(right))
            and left == right
        )
    if left_kind is not right_kind:
        return False
    if left_kind is type(None) or left_kind is str:
        return left == right
    if left_kind is list or left_kind is tuple:
        return len(left) == len(right) and all(_equal(a, b) for a, b in zip(left, right))
    if left_kind is dict:
        if len(left) != len(right):
            return False
        tagged = {}
        for key, value in right.items():
            tag = _key_tag(key)
            if tag is None:
                return False
            tagged[tag] = value
        for key, value in left.items():
            tag = _key_tag(key)
            if tag is None or tag not in tagged or not _equal(value, tagged[tag]):
                return False
        return True
    # An exact helper must not delegate completion to arbitrary object equality.
    return False


def verify_state(*, text=None, controls=()):
    checks = copy.deepcopy(list(controls))
    if text is not None and type(text) is not str:
        raise ValueError("verification_text_required")
    for check in checks:
        if (
            type(check) is not dict
            or any(type(key) is not str for key in check)
            or type(check.get("label")) is not str
            or len(check) < 2
        ):
            raise ValueError("control_check_requires_label_and_expected_fields")

    if not checks and (text is None or not text.strip()):
        raise ValueError("completion_condition_required")

    def verify(ctx, state):
        if type(state) is not dict or any(type(key) is not str for key in state):
            return False
        if text is not None:
            observed_text = state.get("text", "")
            if type(observed_text) is not str or text not in observed_text:
                return False
        observed_controls = state.get("controls", [])
        if checks and (
            (type(observed_controls) is not list and type(observed_controls) is not tuple)
            or any(
                type(control) is not dict or any(type(key) is not str for key in control)
                for control in observed_controls
            )
        ):
            return False
        for check in checks:
            matches = [
                control
                for control in observed_controls
                if _equal(control.get("label"), check["label"])
            ]
            if len(matches) != 1 or any(
                key not in matches[0] or not _equal(matches[0][key], value)
                for key, value in check.items()
            ):
                return False
        return True

    return verify
