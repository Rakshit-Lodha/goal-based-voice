import asyncio
import os

from agent import tools
from core.session import STATE, snapshot


def _run(coro):
    return asyncio.run(coro)


def _install_otp(monkeypatch):
    requested = []

    async def fake_request_otp(provider):
        requested.append(provider)
        return "1234"

    monkeypatch.setattr(tools.consent, "request_otp", fake_request_otp)
    return requested


def test_gold_manual_asset_end_to_end_plan_eval(monkeypatch):
    """Gold scenario reaches a complete deterministic plan with manual gold captured and portfolio gold allocated."""
    requested_otps = _install_otp(monkeypatch)

    risk = _run(tools.assess_risk_profile({
        "answers": ["I would hold steady", "I prefer balanced growth"],
    }))
    assert risk["risk_profile"] == "balanced"

    family = _run(tools.add_family({
        "spouse_age": 27,
        "children": [{"age": 3}],
        "dependents_count": 0,
    }))
    assert family["children"] == [{"age": 3}]

    mf = _run(tools.pull_mf_central({
        "user_confirmed_consent": True,
        "consent_context": "User agreed after Maya explained MF Central and its portfolio-only use.",
    }))
    assert mf["total_value"] == 1_800_000
    assert mf["underperformers"] == ["Midcap Momentum Fund", "Thematic Infra Fund"]

    aa = _run(tools.pull_account_aggregator({
        "user_confirmed_consent": True,
        "consent_context": "User agreed after Maya explained Finvu AA consent and data use.",
    }))
    assert aa["monthly_income"] == 150_000
    assert aa["monthly_expenses"] == 70_000
    assert aa["monthly_emi"] == 25_000

    gold = _run(tools.add_manual_asset({
        "name": "Family gold",
        "asset_type": "gold",
        "value": 500_000,
    }))
    assert gold["additional_assets"] == [
        {"name": "Family gold", "asset_type": "gold", "value": 500_000}
    ]

    confirmed = _run(tools.confirm_financial_snapshot({
        "user_confirmed_financial_data": True,
        "user_answered_additional_assets": True,
        "confirmation_context": "User confirmed AA values and added family gold.",
    }))
    assert confirmed["financial_snapshot_confirmed"] is True

    emergency = _run(tools.add_goal({
        "name": "Emergency fund",
        "horizon_years": 1,
        "priority": 1,
    }))
    assert emergency["inflated_target"] == 570_000

    retirement = _run(tools.add_goal({
        "name": "Retirement",
        "target_amount_today": 30_000_000,
        "horizon_years": 32,
        "priority": 2,
    }))
    assert retirement["inflation_used"] == 0.06

    _run(tools.project_existing_corpus({"goal_name": "Emergency fund"}))
    emergency_gap = _run(tools.compute_gap_and_sip({"goal_name": "Emergency fund"}))
    assert emergency_gap["required_sip"] == 0

    _run(tools.project_existing_corpus({"goal_name": "Retirement"}))
    retirement_gap = _run(tools.compute_gap_and_sip({"goal_name": "Retirement"}))
    assert retirement_gap["required_sip"] > 0
    assert retirement_gap["expected_return_used"] == 0.11

    portfolio = _run(tools.build_goal_portfolio({"goal_name": "Retirement"}))
    assert portfolio["horizon_bucket"] == "long"
    assert len(portfolio["phases"]) == 3
    assert portfolio["current_phase"]["allocation"]["gold"] == 0.05
    assert any(f["bucket"] == "gold" for f in portfolio["current_phase"]["funds"])
    assert any(f["fund"] == "Gold ETF Fund of Fund" for f in portfolio["current_phase"]["funds"])

    pdf = _run(tools.generate_plan_pdf({}))
    assert pdf["url"].startswith("/output/plan_rakshit_")
    assert os.path.exists(STATE.plan_pdf_path)

    state = snapshot(last_event="gold_eval")
    assert requested_otps == ["MF Central", "Finvu Account Aggregator"]
    assert state["additional_assets"][0]["asset_type"] == "gold"
    assert state["financial_snapshot_confirmed"] is True
    assert state["progress"]["pdf"] == "done"
