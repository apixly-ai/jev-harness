"""Repeated multi-team browser task: differing workspaces, per-team truth, shared budgets."""

import ast
import importlib
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest


@pytest.fixture
def browser(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "benchmarks"))
    return importlib.import_module("browser_cold")


@pytest.fixture
def batch(browser):
    return importlib.import_module("browser_batch")


def post(url, body):
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "x"}
    )
    return json.loads(urllib.request.urlopen(request).read())


def expected_draft(state, team):
    return dict(state.expected(team))


def test_contract_names_every_team_but_no_project_answers(batch):
    case = batch.batch_contract()
    assert [t["id"] for t in case["teams"]] == [t["id"] for t in batch.TEAMS]
    assert len(case["values"]) == 2 * len(batch.TEAMS)
    prompt = batch.batch_prompt(case)
    assert all(t["name"] in prompt and t["timezone"] in prompt for t in case["teams"])
    for team in batch.TEAMS:
        for project in team["projects"]:
            assert project["name"] not in prompt
    assert "prefer" not in prompt.lower() and "jev" not in prompt.lower()


def test_workspaces_differ_so_no_single_click_sequence_fits(batch):
    plans = {row["team"]: row["steps"] for row in batch.program_steps(batch.batch_contract())}
    labels = {team: {label for _, label, _ in steps} for team, steps in plans.items()}
    assert plans["atlas"][0] == ("click", "Atlas workspace", None)
    assert all(steps[0][1] == "All teams" for team, steps in plans.items() if team != "atlas")
    assert "Sources" in labels["borealis"] and "Use Ingest" in labels["borealis"]
    assert "Report name" in labels["borealis"] and "Digest title" not in labels["borealis"]
    assert {"General", "Schedule"} <= labels["cobalt"]
    assert sum(label == "Next projects" for _, label, _ in plans["delta"]) == 2
    assert "Ember preview inbox" in " ".join(labels["ember"])
    assert "I reviewed these settings" in labels["fjord"]
    sequences = {tuple(label for _, label, _ in steps[2:]) for steps in plans.values()}
    assert len(sequences) == len(plans)
    assert 80 <= sum(len(steps) for steps in plans.values()) <= 120


def test_server_routes_team_pages_and_checks_each_team_independently(browser, batch):
    case = batch.batch_contract()
    with browser.DraftServer(case) as server:
        index = urllib.request.urlopen(server.url).read().decode()
        assert all(f'href="/team/{t["id"]}"' in index for t in batch.TEAMS)
        page = urllib.request.urlopen(server.url + "team/borealis").read().decode()
        assert "Borealis workspace" in page and "All teams" in page
        assert "expected" not in page and "check_goal" not in page
        for path in ("team/unknown", "team/atlas/extra"):
            with pytest.raises(urllib.error.HTTPError):
                urllib.request.urlopen(server.url + path)
        for path in ("draft", "team/unknown/draft", "team/atlas/send"):
            with pytest.raises(urllib.error.HTTPError):
                post(server.url + path, {})
        state = server.state
        assert state.check_goal()["problems"] == [t["id"] + ":not_saved" for t in batch.TEAMS]
        for team in batch.TEAMS:
            post(server.url + f"team/{team['id']}/draft", expected_draft(state, team["id"]))
        checked = state.check_goal()
        assert checked["passed"] is True and checked["passed_teams"] == len(batch.TEAMS)
        wrong = {**expected_draft(state, "delta"), "projects": ["search"]}
        post(server.url + "team/delta/draft", wrong)
        checked = state.check_goal()
        assert checked["passed"] is False
        assert checked["teams"]["delta"]["problems"] == ["projects", "multiple_save_attempts"]
        assert checked["teams"]["atlas"]["passed"] is True
        assert "search" not in json.dumps(checked)


def test_batch_tools_offer_repeated_focused_runs_and_single_keeps_one_shot(browser):
    single = {t["name"]: t for t in browser.tools(True)}["run_script"]
    assert "One execution" in single["description"]
    assert "focus" not in single["inputSchema"]["properties"]
    batch = {t["name"]: t for t in browser.tools(True, budgets=browser.BUDGETS["batch"])}
    run = batch["run_script"]
    assert "focus" in run["inputSchema"]["properties"]
    assert "Up to 12 executions" in run["description"]
    assert "200 browser effects" in run["description"] and "300 provider" in run["description"]
    assert "prefer" not in run["description"].lower()
    native = {t["name"] for t in browser.tools(False, budgets=browser.BUDGETS["batch"])}
    assert "run_script" not in native and {"observe", "act", "shell"} <= native


def test_run_script_gates_executions_focus_and_shared_provider_budget(browser):
    session = object.__new__(browser.BrowserColdSession)
    session.optional, session.executions = True, 0
    session.budgets = dict(browser.BUDGETS["single"])
    session.provider_requests_used, session.jev_seconds_used = 0, 0.0
    with pytest.raises(ValueError, match="focus_not_offered"):
        session.run_script("task.py", focus="Atlas")
    session.executions = 1
    with pytest.raises(ValueError, match="already_attempted"):
        session.run_script("task.py")
    session.budgets, session.executions = dict(browser.BUDGETS["batch"]), 3
    session.provider_requests_used = 299
    with pytest.raises(ValueError, match="provider_budget_exhausted"):
        session.run_script("task.py", focus="Cobalt")
    session.provider_requests_used, session.jev_seconds_used = 0, 599.5
    with pytest.raises(ValueError, match="provider_budget_exhausted"):
        session.run_script("task.py", focus="Cobalt")


def test_batch_broker_bound_and_direct_canary_plan_are_consistent(browser, batch):
    with pytest.raises(ValueError, match="invalid_browser_effect_budget"):
        browser.BrowserBroker(
            object(), allowed_origin="http://x", values={}, check_goal=dict, max_effects=201
        )
    source = browser.batch_direct_canary(batch.batch_contract())
    compile(source, "canary", "exec")
    plan = json.loads(ast.literal_eval(source.split("\n", 1)[0].removeprefix("PLAN = ")))
    assert plan == json.loads(json.dumps(batch.program_steps(batch.batch_contract())))
