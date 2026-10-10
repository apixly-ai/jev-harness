"""Program-owned decision diagnostics. Never expose exception text or bound values."""

import re

from jev_context.provider import ProviderError

HTTP_CODE_PATTERN = r"http_[1-5][0-9]{2}_body_suppressed"
PROVIDER_CODES = frozenset(
    {
        "credentials_missing",
        "credentials_invalid",
        "credential_file_permissions",
        "client_closed",
        "response_too_large",
        "transport_failed_usage_unknown",
        "response_invalid_usage_unknown",
        "retry_exhausted",
        "provider_unavailable",
    }
)
SELECTION_CODES = frozenset(
    {
        "below_min_top_probability",
        "below_min_margin",
        "below_min_confidence",
        "selected_option_not_top",
        "model_review",
        "no_matching_candidate",
        "invalid_selection",
        "unresolved_selection",
        "decision_failed",
    }
)


def safe_provider_code(value):
    if isinstance(value, str) and (
        value in PROVIDER_CODES or re.fullmatch(HTTP_CODE_PATTERN, value)
    ):
        return value
    return None


def provider_failure_code(error):
    if isinstance(error, ProviderError):
        return safe_provider_code(error.code) or "provider_unavailable"
    return "provider_unavailable"


def stage_context(extra=None):
    extra = extra or {}
    if "parameter" not in extra:
        return {"stage": "tool_selection"}
    context = {"stage": "parameter_selection"}
    # These are identifiers supplied by the trusted binding callback, never model output.
    for source, target in (("selected_tool", "tool_id"), ("parameter", "parameter")):
        if isinstance(extra.get(source), str) and extra[source]:
            context[target] = extra[source]
    return context


def selection_diagnostic(packet, records, stage):
    telemetry = packet.get("telemetry", {})
    codes = []
    failures = telemetry.get("provider_failure_codes", [])
    for code in failures if isinstance(failures, list) else []:
        admitted = safe_provider_code(code)
        if admitted and admitted not in codes:
            codes.append(admitted)
    reasons = telemetry.get("selection_review_reasons", [])
    for reason in reasons if isinstance(reasons, list) else []:
        code = reason.get("reason") if isinstance(reason, dict) else None
        if isinstance(code, str) and code in SELECTION_CODES and code not in codes:
            codes.append(code)
    selected = packet.get("selected_ids", [])
    if not codes:
        if not packet.get("ok"):
            codes.append("provider_unavailable")
        elif not packet.get("complete") or packet.get("review_ids"):
            codes.append("unresolved_selection")
        elif not selected:
            codes.append("no_matching_candidate")
        elif len(selected) != 1 or selected[0] not in {record["id"] for record in records}:
            codes.append("invalid_selection")
    if not codes:
        return None
    return {**stage, "reason_codes": codes, "automatic_retry": False}
