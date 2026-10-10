"""Tool registration and dependent, semantically described parameter domains."""

import copy
import inspect
import itertools
from dataclasses import dataclass

from .callbacks import provider_arity, require_synchronous
from .engine import Action, DecisionStop, Workflow, _json


@dataclass(frozen=True)
class Option:
    id: str
    description: str
    value: object

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("option_id_required")
        if not isinstance(self.description, str) or not self.description:
            raise ValueError("option_description_required")
        _json(self.value)


@dataclass(frozen=True)
class Parameter:
    description: str
    choices: object
    depends_on: tuple = ()

    def __post_init__(self):
        if not isinstance(self.description, str) or not self.description:
            raise ValueError("parameter_description_required")
        if not callable(self.choices) and not isinstance(self.choices, (list, tuple)):
            raise ValueError("parameter_domain_must_be_list_or_callable")
        if callable(self.choices):
            provider_arity(self.choices)
        if not isinstance(self.depends_on, tuple) or any(
            not isinstance(x, str) for x in self.depends_on
        ):
            raise ValueError("invalid_parameter_dependencies")


class Task(Workflow):
    """Default: select tool, then bind parameters in dependency order. No argument generation.

    Explicit strategy='joint' retains small complete-call enumeration for comparison.
    """

    def __init__(self, *, observe, verify, authorize=None, strategy="staged"):
        if not callable(observe) or not callable(verify):
            raise ValueError("observe_and_verify_required")
        if authorize is not None and not callable(authorize):
            raise ValueError("authorization_callable_required")
        if strategy not in ("staged", "joint"):
            raise ValueError("unknown_binding_strategy")
        for callback, role in ((observe, "observe"), (verify, "verify"), (authorize, "authorize")):
            if callback is not None:
                require_synchronous(callback, role)
        self._observe, self._verify, self._authorize = observe, verify, authorize
        self.strategy, self._tools, self._offered = strategy, {}, {}

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
        parameters = {
            key: value if isinstance(value, Parameter) else Parameter(key, value)
            for key, value in (parameters or {}).items()
        }
        for callback, role in ((available, "available"), (result_context, "result_context")):
            if callback is not None and not callable(callback):
                raise ValueError("tool_callback_required")
            if callback is not None:
                require_synchronous(callback, role)
        order, unresolved = [], dict(parameters)
        while unresolved:
            ready = [key for key, p in unresolved.items() if set(p.depends_on) <= set(order)]
            if not ready:
                raise ValueError("invalid_parameter_dependencies")
            for key in ready:
                order.append(key)
                del unresolved[key]

        def register(function):
            require_synchronous(function, "execute")
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
            self._tools[tool_name] = dict(
                function=function,
                description=description,
                parameters={
                    key: Parameter(
                        p.description,
                        p.choices if callable(p.choices) else copy.deepcopy(p.choices),
                        p.depends_on,
                    )
                    for key, p in parameters.items()
                },
                order=order,
                irreversible=irreversible,
                available=available,
                result_context=result_context,
            )
            return function

        return register

    def observe(self, ctx):
        return self._observe(ctx)

    def verify(self, ctx, state):
        return self._verify(ctx, state)

    def authorize(self, ctx, action):
        return self._authorize(ctx, action) if self._authorize is not None else False

    def _domain(self, spec, ctx, state, bound):
        provider = spec.choices
        if callable(provider):
            argc = provider_arity(provider)
            domain = (
                provider(ctx, copy.deepcopy(state), copy.deepcopy(bound))
                if argc == 3
                else provider(ctx, copy.deepcopy(state))
            )
        else:
            domain = provider
        if not isinstance(domain, (list, tuple)):
            raise ValueError("parameter_domain_must_be_list")
        options = [
            x if isinstance(x, Option) else Option(str(i), _json(x), x)
            for i, x in enumerate(domain)
        ]
        if len({x.id for x in options}) != len(options):
            raise ValueError("duplicate_option_ids")
        if len(options) > 253:
            raise DecisionStop("needs_review", "parameter_domain_too_large")
        return options

    def describe(self):
        return {
            name: {
                "description": tool["description"],
                "irreversible": tool["irreversible"],
                "parameters": {
                    key: {
                        "description": p.description,
                        "depends_on": list(p.depends_on),
                        "dynamic": callable(p.choices),
                    }
                    for key, p in tool["parameters"].items()
                },
            }
            for name, tool in self._tools.items()
        }

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
            domains, visible = [], {}
            unavailable = False
            for key, spec in tool["parameters"].items():
                visible[key] = {
                    "description": spec.description,
                    "depends_on": list(spec.depends_on),
                }
                if not spec.depends_on:
                    options = self._domain(spec, ctx, state, {})
                    if not options:
                        unavailable = True
                        break
                    domains.append((key, options))
                    visible[key]["choices"] = [
                        {"id": x.id, "description": x.description} for x in options
                    ]
            if unavailable:
                continue
            if self.strategy == "staged":
                actions.append(
                    Action(
                        name,
                        _json(
                            {"tool": name, "purpose": tool["description"], "parameters": visible}
                        ),
                        {"tool": name},
                        tool["irreversible"],
                    )
                )
            else:
                if any(p.depends_on for p in tool["parameters"].values()):
                    raise ValueError("joint_strategy_has_no_dependent_domains")
                count = 1
                for _, options in domains:
                    count *= len(options)
                if len(actions) + count > 250:
                    raise DecisionStop("needs_review", "narrow_joint_parameter_domains")
                for index, combination in enumerate(itertools.product(*(d[1] for d in domains))):
                    args = {
                        key: copy.deepcopy(option.value)
                        for (key, _), option in zip(domains, combination)
                    }
                    labels = {
                        key: option.description for (key, _), option in zip(domains, combination)
                    }
                    actions.append(
                        Action(
                            f"{name}:{index}",
                            _json(
                                {"tool": name, "purpose": tool["description"], "parameters": labels}
                            ),
                            {"tool": name, "arguments": args},
                            tool["irreversible"],
                        )
                    )
        self._offered = {a.id: copy.deepcopy(a) for a in actions}
        return actions

    def bind(self, ctx, state, action, choose):
        if action != self._offered.get(action.id):
            raise ValueError("action_not_offered")
        if self.strategy == "joint":
            return action
        tool = self._tools[action.params["tool"]]
        args, references = {}, {}
        for key in tool["order"]:
            spec = tool["parameters"][key]
            options = self._domain(spec, ctx, state, args)
            if not options:
                raise DecisionStop("needs_context", "empty_parameter_domain:" + key)
            if len(options) == 1:
                option = options[0]  # No semantic choice needed.
            else:
                packet = choose(
                    [{"id": x.id, "text": x.description} for x in options],
                    "Select parameter "
                    + key
                    + " for tool "
                    + action.params["tool"]
                    + ": "
                    + spec.description,
                    {
                        "selected_tool": action.params["tool"],
                        "tool_contract": self.describe()[action.params["tool"]],
                        "parameter": key,
                        "parameter_description": spec.description,
                        "bound_references": references,
                    },
                )
                selected = packet["selected_ids"]
                if not packet["ok"] or not packet["complete"] or len(selected) != 1:
                    raise DecisionStop("needs_review", "unresolved_parameter:" + key)
                matches = [x for x in options if x.id == selected[0]]
                if len(matches) != 1:
                    raise DecisionStop("needs_review", "invalid_parameter_selection:" + key)
                option = matches[0]
            args[key] = copy.deepcopy(option.value)
            references[key] = {"id": option.id, "description": option.description}
        bound = Action(
            action.id,
            _json(
                {
                    "tool": action.params["tool"],
                    "purpose": tool["description"],
                    "selected_parameters": references,
                }
            ),
            {"tool": action.params["tool"], "arguments": args},
            action.irreversible,
        )
        self._offered[action.id] = copy.deepcopy(bound)
        return bound

    def execute(self, ctx, action):
        if action != self._offered.get(action.id) or "arguments" not in action.params:
            raise ValueError("action_not_bound")
        return self._tools[action.params["tool"]]["function"](
            **copy.deepcopy(action.params["arguments"])
        )

    def result_context(self, ctx, action, result):
        admission = self._tools[action.params["tool"]]["result_context"]
        return admission(result) if admission is not None else None
