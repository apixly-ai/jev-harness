"""Thin workspace discovery task: inputs include root, optional queries, markers and output.

Markers are known schema prefixes, not field answers or navigation routes.
Customize verify for your source contract. Jev inference is billable.
"""

import apixly_jev_harness as jev


def build(inputs):
    markers, output = inputs["markers"], inputs["output"]
    if type(markers) is not dict or not markers:
        raise ValueError("nonempty_marker_contract_required")
    if any(type(x) is not str or not x.strip() for pair in markers.items() for x in pair):
        raise ValueError("nonempty_marker_contract_required")
    store = jev.EvidenceStore()
    pack = jev.WorkspaceTools(inputs["root"], store, queries=inputs.get("queries", []))
    checks = {
        label: lambda row, prefix=prefix: prefix in row["text"] for label, prefix in markers.items()
    }

    def verify(ctx, seen):
        return all(
            any(row["label"] == label and checks[label](row) for row in seen["evidence"]["records"])
            for label in markers
        )

    return jev.EvidenceTask(
        [pack],
        store=store,
        labels=list(markers),
        output=output,
        verify=verify,
        record_checks=checks,
    )


workflow = jev.TaskScript(build)
