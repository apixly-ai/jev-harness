import apixly_jev_harness as jev


def build(inputs):
    checks = inputs["markers"]
    if type(checks) is not dict or not checks:
        raise ValueError("markers_object_required")
    if not all(type(x) is str and x.strip() for pair in checks.items() for x in pair):
        raise ValueError("marker_labels_and_values_required")
    store = jev.EvidenceStore()
    provider = jev.HttpProvider(inputs["url"], allowed_origins=inputs["allowed_origins"])
    return jev.EvidenceTask(
        [jev.WebTools(provider, store)],
        store=store,
        labels=list(checks),
        output=inputs["output"],
        record_checks={k: lambda row, m=v: m in row["text"] for k, v in checks.items()},
        verify=lambda ctx, seen: all(
            any(
                row["label"] == label and marker in row["text"]
                for row in seen["evidence"]["records"]
            )
            for label, marker in checks.items()
        ),
    )


workflow = jev.TaskScript(build)
