"""Read-only repo tasks for prepared-script execution and neutral route-choice evals.

This module creates trusted synthetic source material, never executes it. Actor inputs
contain source scope and schema/syntax markers only. The source/value oracle and closed
AST state-transition evaluator stay outside those inputs; this is not an AI-authoring
benchmark or proof that a model naturally prefers a particular route.
"""

import ast
import hashlib
import json
from pathlib import Path

VERSIONS = ("2.4.0", "2.5.0")
WORKERS = (
    """def submit(job, state, ack_lost=False):
    if job in state["reserved"]:
        return "duplicate"
    state["deliveries"].append(job)
    if ack_lost:
        return "retry"
    state["reserved"].add(job)
    return "accepted"
""",
    """def submit(job, state, ack_lost=False):
    if job in state["reserved"]:
        return "duplicate"
    state["reserved"].add(job)
    state["deliveries"].append(job)
    if ack_lost:
        state["reserved"].discard(job)
        return "retry"
    return "accepted"
""",
)
TEST_SOURCE = """from src.worker import submit


def test_acked_repeated_submission_delivers_once():
    state = {"reserved": set(), "deliveries": []}
    submit("job-741", state, ack_lost=False)
    submit("job-741", state, ack_lost=False)
    assert len(state["deliveries"]) == 1


def test_lost_ack_retry_delivers_once():
    state = {"reserved": set(), "deliveries": []}
    submit("job-741", state, ack_lost=True)
    submit("job-741", state, ack_lost=False)
    assert len(state["deliveries"]) == 1
"""
POLICIES = (
    "Retry scheduling: enabled while acknowledgement is unconfirmed.",
    "Retry scheduling: enabled after acknowledgement loss; normal acknowledged re-submission stays deduplicated.",
)


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


class _Return(Exception):
    def __init__(self, value):
        self.value = value


def _expression(node, environment):
    if isinstance(node, ast.Constant) and type(node.value) in (str, bool):
        return node.value
    if isinstance(node, ast.Name) and node.id in environment:
        return environment[node.id]
    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "state"
        and isinstance(node.slice, ast.Constant)
        and node.slice.value in ("reserved", "deliveries")
    ):
        return environment["state"][node.slice.value]
    if (
        isinstance(node, ast.Compare)
        and len(node.ops) == len(node.comparators) == 1
        and isinstance(node.ops[0], ast.In)
    ):
        return _expression(node.left, environment) in _expression(node.comparators[0], environment)
    raise ValueError("unsupported_fixture_syntax")


def _method(node):
    if (
        not isinstance(node, ast.Call)
        or not isinstance(node.func, ast.Attribute)
        or node.keywords
        or len(node.args) != 1
        or not isinstance(node.func.value, ast.Subscript)
        or not isinstance(node.func.value.value, ast.Name)
        or node.func.value.value.id != "state"
        or not isinstance(node.func.value.slice, ast.Constant)
    ):
        raise ValueError("unsupported_fixture_syntax")
    container, method = node.func.value.slice.value, node.func.attr
    if (container, method) not in {
        ("reserved", "add"),
        ("reserved", "discard"),
        ("deliveries", "append"),
    }:
        raise ValueError("unsupported_fixture_syntax")
    return container, method


def _statements(nodes, environment, events):
    for node in nodes:
        if isinstance(node, ast.If):
            value = _expression(node.test, environment)
            if type(value) is not bool:
                raise ValueError("fixture_boolean_condition_required")
            _statements(node.body if value else node.orelse, environment, events)
        elif isinstance(node, ast.Return):
            raise _Return(_expression(node.value, environment))
        elif isinstance(node, ast.Expr):
            container, method = _method(node.value)
            argument = _expression(node.value.args[0], environment)
            target = environment["state"][container]
            expected_type = list if container == "deliveries" else set
            if type(target) is not expected_type or type(argument) is not str:
                raise ValueError("unsupported_fixture_state")
            getattr(target, method)(argument)
            events.append(container + "." + method)
        else:
            raise ValueError("unsupported_fixture_syntax")


def analyze_worker(text):
    """Interpret a closed pure subset; no compile/exec/import/IO of fixture source."""
    tree = ast.parse(text)
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise ValueError("unsupported_fixture_syntax")
    function = tree.body[0]
    if (
        function.name != "submit"
        or [argument.arg for argument in function.args.args] != ["job", "state", "ack_lost"]
        or function.args.vararg is not None
        or function.args.kwarg is not None
        or function.args.kwonlyargs
        or function.decorator_list
    ):
        raise ValueError("unsupported_fixture_syntax")
    top_methods = [_method(node.value) for node in function.body if isinstance(node, ast.Expr)]
    if ("reserved", "add") not in top_methods or ("deliveries", "append") not in top_methods:
        raise ValueError("unsupported_fixture_syntax")
    loss = [
        node
        for node in function.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "ack_lost"
    ]
    if len(loss) != 1:
        raise ValueError("unsupported_fixture_syntax")
    profile = {
        "reserve_before_dispatch": top_methods.index(("reserved", "add"))
        < top_methods.index(("deliveries", "append")),
        "lost_ack_discards_reservation": any(
            isinstance(node, ast.Expr) and _method(node.value) == ("reserved", "discard")
            for node in loss[0].body
        ),
    }

    def run(first_lost):
        state, events, returned = {"reserved": set(), "deliveries": []}, [], []
        for ack_lost in (first_lost, False):
            try:
                _statements(
                    function.body, {"job": "job-741", "state": state, "ack_lost": ack_lost}, events
                )
            except _Return as stop:
                returned.append(stop.value)
        return len(state["deliveries"]), events, returned

    count, events, returned = run(True)
    normal, normal_events, normal_returned = run(False)
    return profile, {
        "lost_ack_delivery_count": count,
        "normal_retry_delivery_count": normal,
        "lost_ack_events": events,
        "normal_retry_events": normal_events,
        "lost_ack_returns": returned,
        "normal_retry_returns": normal_returned,
    }


def _test_contract(text):
    tree = ast.parse(text)
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    expected = {
        "test_acked_repeated_submission_delivers_once": [False, False],
        "test_lost_ack_retry_delivers_once": [True, False],
    }
    for name, conditions in expected.items():
        function = functions.get(name)
        if function is None:
            return False
        calls = [
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "submit"
        ]
        observed = []
        for call in calls:
            value = next((kw.value for kw in call.keywords if kw.arg == "ack_lost"), None)
            if not isinstance(value, ast.Constant) or type(value.value) is not bool:
                return False
            observed.append(value.value)
        assertions = [node for node in ast.walk(function) if isinstance(node, ast.Assert)]
        if observed != conditions or len(assertions) != 1:
            return False
        check = assertions[0].test
        if (
            not isinstance(check, ast.Compare)
            or len(check.ops) != 1
            or not isinstance(check.ops[0], ast.Eq)
            or len(check.comparators) != 1
            or not isinstance(check.comparators[0], ast.Constant)
            or check.comparators[0].value != 1
        ):
            return False
    return True


def _current_record(version, worker, simulation):
    return {
        "package_version": version,
        "scenario": "retry_after_lost_ack",
        "test": "test_lost_ack_retry_delivers_once",
        "expected_delivery_count": 1,
        "actual_delivery_count": simulation["lost_ack_delivery_count"],
        "normal_retry_delivery_count": simulation["normal_retry_delivery_count"],
        "events": simulation["lost_ack_events"],
        "status": "failed" if simulation["lost_ack_delivery_count"] != 1 else "passed",
        "worker_sha256": _sha(worker),
        "record_origin": "trusted_fixture_pure_state_transition",
    }


def fixture(directory, level="medium", variant=0):
    if (
        level not in ("short", "medium", "missing")
        or type(variant) is not int
        or variant not in (0, 1)
    ):
        raise ValueError("unknown_repository_fixture")
    directory = Path(directory).absolute()
    directory.mkdir(parents=True, exist_ok=False)
    version = VERSIONS[variant]
    manifest = {"name": "delivery-worker", "version": version, "entry": "src/worker.py"}
    files = {"package.json": _json(manifest)}
    if level == "short":
        goal = "Read package.json in this read-only checkout and save source evidence for its package version under version."
        requirements = {"version": '"version":'}
        expected = {"version": "package.json"}
        values = {"version": f'"version": "{version}"'}
        profile = simulation = None
    else:
        worker = WORKERS[variant]
        profile, simulation = analyze_worker(worker)
        current = _current_record(version, worker, simulation)
        files.update(
            {
                "README.md": "# Delivery worker\nSupport observed repeated dispatch after retry. This read-only checkout includes the package manifest, worker, delivery settings, test source, recorded runs and release history. Investigate current behavior and distinguish it from earlier releases.\n",
                "src/worker.py": worker,
                "tests/test_worker.py": TEST_SOURCE,
                "tests/results/previous.json": _json(
                    {
                        "package_version": "1.9.0",
                        "scenario": "retry_after_lost_ack",
                        "actual_delivery_count": 1,
                        "retry_enabled": False,
                        "status": "passed",
                    }
                ),
                "docs/releases.md": f"# Release history\n\n## v{version}\n{POLICIES[variant]}\nDelivery mode: at-least-once.\n\n## v1.9.0\nRetry scheduling: disabled. Jobs awaiting a missing acknowledgement are not resubmitted.\n",
                "config/delivery.json": _json(
                    {
                        "release": version,
                        "retry_enabled": True,
                        "receipt_timeout_ms": 250 if variant == 0 else 400,
                        "delivery_mode": "at-least-once",
                    }
                ),
            }
        )
        if level != "missing":
            files["tests/results/current.json"] = _json(current)
        goal = "Investigate the reported repeated dispatch after retry in the current read-only delivery-worker checkout. Save source implementation evidence, a recorded current test result proving the observed behavior, and current-release counterevidence to the claim that retries are disabled, under implementation, reproduction and counterevidence. If a required source is unavailable, preserve that gap instead of declaring the investigation complete."
        requirements = {
            "implementation": "def submit(",
            "reproduction": '"scenario":',
            "counterevidence": "## v",
        }
        expected = {
            "implementation": "src/worker.py",
            "reproduction": "tests/results/current.json",
            "counterevidence": "docs/releases.md",
        }
        values = {
            "implementation": 'state["deliveries"].append(job)\n    if ack_lost:\n        return "retry"\n    state["reserved"].add(job)'
            if variant == 0
            else 'state["reserved"].add(job)\n    state["deliveries"].append(job)\n    if ack_lost:\n        state["reserved"].discard(job)',
            "reproduction": f'"package_version": "{version}"',
            "counterevidence": f"## v{version}\n{POLICIES[variant]}",
        }
    for relative, text in files.items():
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
    return {
        "family": "repository_sources",
        "level": level,
        "variant": variant,
        "track": "prepared_script_execution; authoring_not_measured",
        "goal": goal,
        "inputs": {
            "kind": "files",
            "root": str(directory),
            "queries": ["version"] if level == "short" else ["retry", "submit", "ack"],
            "requirements": requirements,
        },
        "expected": expected,
        "expected_sources": dict(expected),
        "expected_values": values,
        "source_directory": str(directory),
        "oracle": {
            "version": version,
            "profile": profile,
            "simulation": simulation,
            "missing_record": level == "missing",
            "source_sha256": {relative: _sha(text) for relative, text in files.items()},
        },
        "planned_budget": {
            "max_steps": 6 if level == "short" else 16,
            "required_fields": len(requirements),
            "source_files": len(files),
        },
    }


def mechanical_check(case):
    root = Path(case["source_directory"])
    try:
        manifest = json.loads((root / "package.json").read_text(encoding="utf-8"))
        hashes = {
            relative: _sha((root / relative).read_text(encoding="utf-8"))
            for relative in case["oracle"]["source_sha256"]
        }
        same_sources = hashes == case["oracle"]["source_sha256"]
        if case["level"] == "short":
            return {
                "passed": same_sources and manifest["version"] == case["oracle"]["version"],
                "record_present": None,
                "record_consistent": None,
                "profile": None,
                "simulation": None,
            }
        worker = (root / "src/worker.py").read_text(encoding="utf-8")
        profile, simulation = analyze_worker(worker)
        test_valid = _test_contract((root / "tests/test_worker.py").read_text(encoding="utf-8"))
        path = root / "tests/results/current.json"
        present = path.exists()
        record_ok = (
            json.loads(path.read_text(encoding="utf-8"))
            == _current_record(manifest["version"], worker, simulation)
            if present
            else None
        )
        return {
            "passed": same_sources
            and manifest["version"] == case["oracle"]["version"]
            and profile == case["oracle"]["profile"]
            and simulation == case["oracle"]["simulation"]
            and test_valid
            and present != case["oracle"]["missing_record"]
            and (record_ok is True or not present),
            "record_present": present,
            "record_consistent": record_ok,
            "profile": profile,
            "simulation": simulation,
            "test_contract_valid": test_valid,
        }
    except (OSError, ValueError, KeyError, TypeError, SyntaxError):
        return {"passed": False, "reason": "fixture_source_or_transition_invalid"}


def independent_check(case, report_path, *, captures_path=None):
    """Keep old shape, add whole-source identity/version/semantic proof checks."""
    from open_tasks import independent_check as original_check

    checked = mechanical_check(case)
    try:
        base = original_check(case, report_path, captures_path=captures_path)
        records = json.loads(Path(report_path).read_text(encoding="utf-8"))["records"]
        if type(records) is not list:
            raise ValueError("records_required")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {
            "passed": False,
            "reason": "artifact_missing_or_invalid",
            "mechanical_fixture_valid": checked["passed"],
        }
    matches = {}
    root = Path(case["source_directory"])
    for label, relative in case["expected"].items():
        matching = []
        for row in records:
            if type(row) is not dict or row.get("label") != label:
                continue
            try:
                body = (root / relative).read_text(encoding="utf-8")
                offset, end = row.get("offset"), row.get("end")
                if (
                    row.get("source") != "workspace:" + relative
                    or type(row.get("total")) is not int
                    or row["total"] != len(body)
                    or type(offset) is not int
                    or type(end) is not int
                    or not 0 <= offset <= end <= len(body)
                    or row.get("text") != body[offset:end]
                    or row.get("sha256") != _sha(body)
                ):
                    continue
                quote = row["text"]
                if case["level"] != "short" and label == "reproduction":
                    record = json.loads(quote)
                    semantic = record == _current_record(
                        case["oracle"]["version"],
                        (root / "src/worker.py").read_text(encoding="utf-8"),
                        case["oracle"]["simulation"],
                    )
                else:
                    semantic = case["expected_values"][label] in quote
                matching.append(bool(semantic))
            except (OSError, ValueError, KeyError, TypeError):
                matching.append(False)
        matches[label] = base.get("labels", {}).get(label, False) and any(matching)
    return {
        "passed": checked["passed"] and all(matches.values()),
        "labels": matches,
        "records": len(records),
        "mechanical_fixture_valid": checked["passed"],
        "quality_scope": "source-authenticated required facts; not schema-marker success",
    }
