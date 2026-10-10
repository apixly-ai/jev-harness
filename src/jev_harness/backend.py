"""Native Choice backend on the public Jev Filter typed-batch API."""

from contextvars import ContextVar
from functools import wraps

from jev_context.provider import Client
from jev_context.provider import evaluate as provider_evaluate
from jev_filter import analysis as core
from jev_filter.batch import run as native_run

_ACTIVE = ContextVar("jev_harness_transport", default=None)


class Session:
    def __init__(self, client):
        self.client = client

    def run(self, items, **kwargs):
        before = dict(self.client.stats)
        results = []
        for item in items:
            try:
                row = {
                    "id": item["id"],
                    **provider_evaluate(item["request"], self.client, cache=None),
                }
            except Exception as error:
                row = {
                    "id": item["id"],
                    "ok": False,
                    "error_type": type(error).__name__,
                    "usage_complete": False,
                }
            results.append(row)
        delta = {key: self.client.stats[key] - before[key] for key in before}
        return {
            "ok": all(row["ok"] for row in results),
            "results": results,
            "usage": {
                key: sum(row.get("usage", {}).get(key, 0) for row in results)
                for key in ("input_tokens", "output_tokens")
            },
            "usage_complete": all(
                row["ok"] and row.get("usage_complete", False) for row in results
            ),
            "transport": delta,
            "unknown_usage_attempts": max(0, delta["requests"] - sum(row["ok"] for row in results)),
            "workers": 1,
            "cache_enabled": False,
        }


def session_run(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with Client(pooled=True) as client:
            token = _ACTIVE.set(Session(client))
            try:
                return function(*args, **kwargs)
            finally:
                _ACTIVE.reset(token)

    return wrapped


def evaluate(parts, task, workers, spec):
    if spec.get("mode") != "choose":
        return core.evaluate(parts, task, workers, spec)
    planned = core.plan(parts, task, spec)
    if not planned["items"]:
        return {p["id"]: {"status": "NEEDS_NARROWING", "decision": "REVIEW"} for p in parts}, {
            "ok": True,
            "usage_complete": True,
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "requests": 0,
        }
    session = _ACTIVE.get()
    result = native_run(
        planned["items"],
        workers=workers,
        cache=None,
        **({"runner": session.run} if session is not None else {}),
    )
    row = result["results"][0]
    answer = row.get("answers", {}).get("target", {})
    choice = answer.get("choice", "REVIEW")
    policy = spec.get("uncertainty", {})
    probabilities = answer.get("probabilities", {})
    reasons = []
    if row.get("ok"):
        ranked = sorted(probabilities.values(), reverse=True)
        top = ranked[0] if ranked else None
        margin = top - (ranked[1] if len(ranked) > 1 else 0) if ranked else None
        for metric, actual in [
            ("top_probability", top),
            ("margin", margin),
            ("confidence", answer.get("confidence")),
        ]:
            floor = policy.get("min_" + metric, 0)
            if floor and (actual is None or actual < floor):
                reasons.append(
                    {"reason": "below_min_" + metric, "actual": actual, "threshold": floor}
                )
        if probabilities.get(choice) != top:
            reasons.append({"reason": "selected_option_not_top"})
    if not row.get("ok") or reasons:
        choice = "REVIEW"
    selected = planned["routes"]["choose"].get(choice)
    judgments = {
        p["id"]: {
            "status": "OK" if row.get("ok") else "UNAVAILABLE",
            "decision": "REVIEW"
            if choice == "REVIEW"
            else ("MATCH" if p["id"] == selected else "EXCLUDE"),
            "review_reasons": reasons,
        }
        for p in parts
    }
    telemetry = {k: v for k, v in result.items() if k != "results"}
    model = row.get("model")
    telemetry.update(
        selection=answer,
        model_requested=spec.get("model", "jev-1.13.0"),
        model_resolved=model,
        models={model: result.get("usage")} if model else {},
        selection_review_reasons=reasons,
    )
    return judgments, telemetry
