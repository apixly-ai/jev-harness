from apixly_jev_harness import verify_state


def test_verifier_requires_all_fields_and_unique_matches():
    verify = verify_state(
        text="Complete",
        controls=[{"label": "Name", "value": "Mira"}, {"label": "Flexible", "checked": True}],
    )
    state = {
        "text": "Complete",
        "controls": [{"label": "Name", "value": "Mira"}, {"label": "Flexible", "checked": False}],
    }
    assert verify(None, state) is False
    state["controls"][1]["checked"] = True
    assert verify(None, state) is True
    state["controls"].append({"label": "Name", "value": "Mira"})
    assert verify(None, state) is False


def test_empty_verifier_is_not_a_completion_condition():
    import pytest

    for kwargs in ({}, {"text": ""}, {"text": "   "}, {"controls": []}):
        with pytest.raises(ValueError, match="completion_condition_required"):
            verify_state(**kwargs)


def test_control_only_verifier_remains_valid():
    verify = verify_state(controls=[{"label": "Approved", "checked": True}])
    assert verify(None, {"controls": [{"label": "Approved", "checked": True}]})


def test_missing_control_field_is_not_observed_null():
    verify = verify_state(controls=[{"label": "Name", "value": None}])
    assert verify(None, {"controls": [{"label": "Name"}]}) is False
    assert verify(None, {"controls": [{"label": "Name", "value": None}]}) is True
