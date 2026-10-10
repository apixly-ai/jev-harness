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
