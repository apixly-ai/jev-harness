"""Small tool registry with program-supplied parameter domains."""

import copy
import inspect
import itertools
from dataclasses import dataclass

from .engine import Action, Workflow, _json


@dataclass(frozen=True)
class Option:
    """A parameter candidate whose safe description is separate from its value."""

    id: str
    description: str
    value: object

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("option_id_required")
        if not isinstance(self.description, str) or not self.description:
            raise ValueError("option_description_required")
        _json(self.value)


class Task(Workflow):
    """Register trusted tools and bounded parameter choices, then Engine.run(task).

    parameters maps each argument to a list of JSON values/Options or a read-only
    callable(ctx, observation) returning that list. Jev chooses a fully bound call;
    it cannot introduce a tool, argument or value. This version enumerates the joint
    domain (maximum 253); narrow domains in code instead of silently truncating.
    """

    def __init__(self, *, observe, verify, authorize=None):
        if not callable(observe) or not callable(verify):
            raise ValueError("observe_and_verify_required")
        if authorize is not None and not callable(authorize):
            raise ValueError("authorization_callable_required")
        self._observe = observe
        self._verify = verify
        self._authorize = authorize
        self._tools = {}
        self._offered = {}

    def tool(
        self,
        description,
        *,
        parameters=None,
        name=None,
        irreversible=False,
        available=None,
        result_context=None,
    ):
        """Decorator for a trusted function called with keyword arguments only."""
        parameters = dict(parameters or {})
        if available is not None and not callable(available):
            raise ValueError("available_callable_required")
        if result_context is not None and not callable(result_context):
            raise ValueError("result_context_callable_required")

        def register(function):
            tool_name = name or function.__name__
            Action(tool_name, description, irreversible=irreversible)
            if tool_name in self._tools:
                raise ValueError("duplicate_tool_name")
            signature = inspect.signature(function)
            if any(
                p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD) for p in signature.parameters.values()
            ):
                raise ValueError("explicit_tool_signature_required")
            try:
                signature.bind(**{key: None for key in parameters})
            except TypeError as error:
                raise ValueError("parameter_signature_mismatch") from error
            for domain in parameters.values():
                if not callable(domain) and not isinstance(domain, (list, tuple)):
                    raise ValueError("parameter_domain_must_be_list_or_callable")
            self._tools[tool_name] = {
                "function": function,
                "description": description,
                "parameters": copy.deepcopy(parameters),
                "irreversible": irreversible,
                "available": available,
                "result_context": result_context,
            }
            return function

        return register

    def observe(self, ctx):
        return self._observe(ctx)

    def verify(self, ctx, state):
        return self._verify(ctx, state)

    def authorize(self, ctx, action):
        return self._authorize(ctx, action) if self._authorize is not None else False

    def candidates(self, ctx, state):
        self._offered = {}
        actions = []
        for name, tool in self._tools.items():
            if tool["available"] is not None:
                available = tool["available"](ctx, copy.deepcopy(state))
                if type(available) is not bool:
                    raise ValueError("available_must_return_bool")
                if not available:
                    continue
            domains = []
            for parameter, provider in tool["parameters"].items():
                domain = provider(ctx, copy.deepcopy(state)) if callable(provider) else provider
                if not isinstance(domain, (list, tuple)):
                    raise ValueError("parameter_domain_must_be_list")
                choices = [
                    item if isinstance(item, Option) else Option(str(i), _json(item), item)
                    for i, item in enumerate(domain)
                ]
                if len({option.id for option in choices}) != len(choices):
                    raise ValueError("duplicate_option_ids")
                domains.append((parameter, choices))
            count = 1
            for _, choices in domains:
                count *= len(choices)
            if len(actions) + count > 250:
                raise ValueError("narrow_parameter_domains_to_250_calls")
            for index, combination in enumerate(itertools.product(*(d[1] for d in domains))):
                args = {
                    parameter: copy.deepcopy(option.value)
                    for (parameter, _), option in zip(domains, combination)
                }
                labels = {
                    parameter: {"id": option.id, "description": option.description}
                    for (parameter, _), option in zip(domains, combination)
                }
                action = Action(
                    f"{name}:{index}",
                    _json({"tool": name, "purpose": tool["description"], "parameters": labels}),
                    {"tool": name, "arguments": args},
                    irreversible=tool["irreversible"],
                )
                actions.append(action)
        self._offered = {a.id: copy.deepcopy(a) for a in actions}
        return actions

    def execute(self, ctx, action):
        if action != self._offered.get(action.id):
            raise ValueError("action_not_offered")
        return self._tools[action.params["tool"]]["function"](
            **copy.deepcopy(action.params["arguments"])
        )

    def result_context(self, ctx, action, result):
        admission = self._tools[action.params["tool"]]["result_context"]
        return admission(result) if admission is not None else None
