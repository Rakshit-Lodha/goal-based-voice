import asyncio

from agent import tools
from core.session import STATE


def _run(coro):
    return asyncio.run(coro)


def test_mf_central_requires_explicit_consent():
    """MF Central cannot be pulled before explicit user consent."""
    result = _run(tools.pull_mf_central({}))

    assert result["error"] == "missing: MF Central consent"
    assert "ask permission" in result["instruction"]


def test_account_aggregator_requires_mf_central_first():
    """Finvu Account Aggregator is blocked until MF Central has been pulled."""
    result = _run(tools.pull_account_aggregator({
        "user_confirmed_consent": True,
        "consent_context": "User agreed.",
    }))

    assert result["error"] == "missing: the MF Central pull"
    assert "Call pull_mf_central first" in result["instruction"]


def test_account_aggregator_correction_reuses_existing_consent(monkeypatch):
    """A correction to AA data after the first pull must not request a second OTP."""
    requested = []

    async def fake_request_otp(provider):
        requested.append(provider)
        return "1234"

    monkeypatch.setattr(tools.consent, "request_otp", fake_request_otp)
    STATE.portfolio = {"total_monthly_sip": 12_000}

    first = _run(tools.pull_account_aggregator({
        "user_confirmed_consent": True,
        "consent_context": "User agreed to trigger Finvu OTP.",
    }))
    correction = _run(tools.pull_account_aggregator({
        "user_confirmed_consent": False,
        "consent_context": "Correction after prior consent.",
        "monthly_income": 175_000,
    }))

    assert requested == ["Finvu Account Aggregator"]
    assert first["monthly_income"] == 150_000
    assert correction["monthly_income"] == 175_000


def test_financial_snapshot_confirmation_requires_manual_assets_answer():
    """Goals remain blocked until the user answers the additional-assets question."""
    STATE.aa_assets = {"epf": 450_000, "nps": 50_000, "stocks": 500_000}
    STATE.ratios = {"idle_surplus": 43_000}

    result = _run(tools.confirm_financial_snapshot({
        "user_confirmed_financial_data": True,
        "user_answered_additional_assets": False,
        "confirmation_context": "User confirmed AA but has not answered manual assets.",
    }))

    assert result["error"] == "missing: the additional-investments answer"
    assert "PPF, FDs, gold" in result["instruction"]
