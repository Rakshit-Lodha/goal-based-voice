import asyncio

from agent import tools


def _run(coro):
    return asyncio.run(coro)


def _install_otp(monkeypatch):
    async def fake_request_otp(provider):
        return "1234"

    monkeypatch.setattr(tools.consent, "request_otp", fake_request_otp)


def _named(fn):
    async def wrapped(args):
        return await fn(args)

    wrapped.__name__ = fn.__name__
    return wrapped


def test_registered_tool_names_match_planning_contract():
    """The tool registry exposes the planning tools Maya is allowed to call."""
    expected = [
        "assess_risk_profile",
        "add_family",
        "pull_mf_central",
        "pull_account_aggregator",
        "add_manual_asset",
        "confirm_financial_snapshot",
        "add_goal",
        "project_existing_corpus",
        "compute_gap_and_sip",
        "reprioritize",
        "build_goal_portfolio",
        "generate_plan_pdf",
    ]

    assert [fn.__name__ for fn, *_ in tools.TOOL_SPECS] == expected


def test_gold_plan_uses_expected_tool_call_sequence(monkeypatch):
    """A complete gold-plan scenario calls the right tools in the right deterministic order."""
    _install_otp(monkeypatch)
    calls = []

    async def call(fn, args):
        calls.append(fn.__name__)
        return await fn(args)

    assess_risk_profile = _named(tools.assess_risk_profile)
    add_family = _named(tools.add_family)
    pull_mf_central = _named(tools.pull_mf_central)
    pull_account_aggregator = _named(tools.pull_account_aggregator)
    add_manual_asset = _named(tools.add_manual_asset)
    confirm_financial_snapshot = _named(tools.confirm_financial_snapshot)
    add_goal = _named(tools.add_goal)
    project_existing_corpus = _named(tools.project_existing_corpus)
    compute_gap_and_sip = _named(tools.compute_gap_and_sip)
    build_goal_portfolio = _named(tools.build_goal_portfolio)
    generate_plan_pdf = _named(tools.generate_plan_pdf)

    _run(call(assess_risk_profile, {
        "answers": ["I would hold steady", "I prefer balanced growth"],
    }))
    _run(call(add_family, {
        "spouse_age": 27,
        "children": [{"age": 3}],
        "dependents_count": 0,
    }))
    _run(call(pull_mf_central, {
        "user_confirmed_consent": True,
        "consent_context": "User agreed after Maya explained MF Central.",
    }))
    _run(call(pull_account_aggregator, {
        "user_confirmed_consent": True,
        "consent_context": "User agreed after Maya explained Finvu AA.",
    }))
    _run(call(add_manual_asset, {
        "name": "Family gold",
        "asset_type": "gold",
        "value": 500_000,
    }))
    _run(call(confirm_financial_snapshot, {
        "user_confirmed_financial_data": True,
        "user_answered_additional_assets": True,
        "confirmation_context": "User confirmed AA values and added family gold.",
    }))
    _run(call(add_goal, {
        "name": "Emergency fund",
        "horizon_years": 1,
        "priority": 1,
    }))
    _run(call(add_goal, {
        "name": "Retirement",
        "target_amount_today": 30_000_000,
        "horizon_years": 32,
        "priority": 2,
    }))
    _run(call(project_existing_corpus, {"goal_name": "Emergency fund"}))
    _run(call(compute_gap_and_sip, {"goal_name": "Emergency fund"}))
    _run(call(project_existing_corpus, {"goal_name": "Retirement"}))
    _run(call(compute_gap_and_sip, {"goal_name": "Retirement"}))
    _run(call(build_goal_portfolio, {"goal_name": "Retirement"}))
    _run(call(generate_plan_pdf, {}))

    assert calls == [
        "assess_risk_profile",
        "add_family",
        "pull_mf_central",
        "pull_account_aggregator",
        "add_manual_asset",
        "confirm_financial_snapshot",
        "add_goal",
        "add_goal",
        "project_existing_corpus",
        "compute_gap_and_sip",
        "project_existing_corpus",
        "compute_gap_and_sip",
        "build_goal_portfolio",
        "generate_plan_pdf",
    ]
