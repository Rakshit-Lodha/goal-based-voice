import asyncio

from agent import tools
from core.session import STATE, reset


def test_first_account_aggregator_pull_requests_finvu_otp(monkeypatch):
    requested = []

    async def fake_request_otp(provider):
        requested.append(provider)
        return "1234"

    reset()
    STATE.portfolio = {"total_monthly_sip": 12_000}
    monkeypatch.setattr(tools.consent, "request_otp", fake_request_otp)

    result = asyncio.run(tools.pull_account_aggregator({
        "user_confirmed_consent": True,
        "consent_context": "User agreed to trigger Finvu Account Aggregator OTP.",
    }))

    assert requested == ["Finvu Account Aggregator"]
    assert result["aa_assets"]["epf"] == 450_000
