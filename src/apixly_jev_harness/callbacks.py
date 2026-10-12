"""Declared synchronous callback admission; introspection never invokes the callback."""

import functools
import inspect

CALLBACK_ROLES = frozenset(
    {
        "observe",
        "verify",
        "authorize",
        "execute",
        "available",
        "result_context",
        "choices",
        "candidates",
        "selection_description",
        "bind",
        "context_policy",
    }
)
CALLBACK_CODES = frozenset({"synchronous_callback_required", "provider_signature_unsupported"})
CALLBACK_KINDS = frozenset({"coroutine", "async_generator", "generator"})


class CallbackContractError(ValueError):
    def __init__(self, code, callback, kind=None):
        if (
            code not in CALLBACK_CODES
            or callback not in CALLBACK_ROLES
            or (kind is not None and kind not in CALLBACK_KINDS)
        ):
            raise ValueError("invalid_callback_contract_error")
        self.code, self.callback, self.kind = code, callback, kind
        super().__init__(code)


def project_contract_error(error):
    # Project only fixed enums even if a trusted caller mutates an exception instance.
    code = getattr(error, "code", None)
    role = getattr(error, "callback", None)
    kind = getattr(error, "kind", None)
    result = {
        "code": code
        if isinstance(code, str) and code in CALLBACK_CODES
        else "callback_contract_error"
    }
    if isinstance(role, str) and role in CALLBACK_ROLES:
        result["callback"] = role
    if isinstance(kind, str) and kind in CALLBACK_KINDS:
        result["kind"] = kind
    return result


def require_synchronous(callback, role, *, allow_generator=False):
    # partial's C-level __call__ hides callable-object flavor. Only unwrap partial,
    # not __wrapped__: an explicit synchronous bridge may wrap an async function.
    while isinstance(callback, functools.partial):
        callback = callback.func
    for target in (callback, getattr(callback, "__call__", None)):
        kind = (
            "coroutine"
            if inspect.iscoroutinefunction(target)
            else "async_generator"
            if inspect.isasyncgenfunction(target)
            else "generator"
            if inspect.isgeneratorfunction(target) and not allow_generator
            else None
        )
        if kind:
            raise CallbackContractError("synchronous_callback_required", role, kind)


def provider_arity(callback):
    require_synchronous(callback, "choices")
    try:
        actual = inspect.signature(callback, follow_wrapped=False)
        positional = sum(
            p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
            for p in actual.parameters.values()
        )
        generic = any(p.kind == p.VAR_POSITIONAL for p in actual.parameters.values())
        # Explicit bridges own their call shape. Generic forwarding wrappers retain
        # their advertised delegate contract, checked against the actual entry point.
        signature = inspect.signature(callback) if generic and positional < 3 else actual
    except (TypeError, ValueError):
        raise CallbackContractError("provider_signature_unsupported", "choices") from None
    # Three arguments expose bound parents. Optional keyword-only parameters are fine.
    for count in (3, 2):
        try:
            signature.bind(*([None] * count))
            actual.bind(*([None] * count))
            return count
        except TypeError:
            continue
    raise CallbackContractError("provider_signature_unsupported", "choices")
