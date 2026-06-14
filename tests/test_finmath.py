import math

import pytest

from core import finmath as fm


def test_round_to_500():
    assert fm.round_to_500(12320) == 12500
    assert fm.round_to_500(12200) == 12000
    assert fm.round_to_500(0) == 0


def test_inflation_for_goal():
    assert fm.inflation_for_goal("Daughter's education") == 0.10
    assert fm.inflation_for_goal("Buy a house in Pune") == 0.07
    assert fm.inflation_for_goal("New car") == 0.06


def test_inflate():
    # 1 crore house, 12 years at 7%: 1e7 * 1.07^12
    assert fm.inflate(1e7, 12, 0.07) == pytest.approx(22_521_916, rel=1e-4)
    # 5 lakh at 6% for 1 year
    assert fm.inflate(500_000, 1, 0.06) == pytest.approx(530_000)


def test_financial_ratios():
    r = fm.financial_ratios(100_000, 60_000, 10_000, existing_monthly_sip=12_000)
    assert r["surplus"] == 30_000
    assert r["savings_rate"] == pytest.approx(0.30)
    assert r["savings_band"] == "bad"
    assert r["debt_to_income"] == pytest.approx(0.10)
    assert r["dti_band"] == "average"
    assert r["idle_surplus"] == 18_000


def test_financial_ratios_bands():
    assert fm.financial_ratios(100_000, 65_000)["savings_band"] == "bad"
    assert fm.financial_ratios(100_000, 50_000)["savings_band"] == "average"
    assert fm.financial_ratios(100_000, 30_000)["savings_band"] == "good"
    assert fm.financial_ratios(100_000, 30_000, 25_000)["dti_band"] == "bad"
    assert fm.financial_ratios(100_000, 30_000, 10_000)["dti_band"] == "average"
    assert fm.financial_ratios(100_000, 30_000, 9_000)["dti_band"] == "good"


def test_lumpsum_fv():
    assert fm.lumpsum_fv(100_000, 0.11, 5) == pytest.approx(168_505.8, rel=1e-4)
    assert fm.lumpsum_fv(100_000, 0.07, 0) == pytest.approx(100_000)


def test_sip_fv():
    # 10k/month at 12% for 10 years (annuity-due): ≈ ₹23.23L
    assert fm.sip_fv(10_000, 0.12, 10) == pytest.approx(2_323_391, rel=1e-4)
    assert fm.sip_fv(0, 0.12, 10) == 0.0


def test_required_sip_inverts_sip_fv():
    target = fm.sip_fv(10_000, 0.12, 10)
    assert fm.required_sip(target, 0.12, 10) == pytest.approx(10_000, rel=1e-6)
    assert fm.required_sip(0, 0.12, 10) == 0.0


def test_years_to_target_inverts_sip_fv():
    target = fm.sip_fv(10_000, 0.12, 10)
    assert fm.years_to_target(10_000, target, 0.12) == pytest.approx(10.0, abs=0.05)
    assert fm.years_to_target(0, 100_000, 0.12) == math.inf


def test_blended_growth():
    assert fm.blended_growth(50, 50) == pytest.approx(0.09)
    assert fm.blended_growth(100, 0) == pytest.approx(0.11)
    assert fm.blended_growth(0, 0) == pytest.approx(0.07)


def test_affordability():
    assert fm.affordability(10_000, 20_000) == "comfortable"
    assert fm.affordability(18_000, 20_000) == "tight"
    assert fm.affordability(25_000, 20_000) == "unaffordable"
    assert fm.affordability(5_000, 0) == "unaffordable"


def test_risk_scoring():
    assert fm.score_risk_answer("I would top up and buy more") == 1
    assert fm.score_risk_answer("I'd panic and sell everything") == -1
    assert fm.score_risk_answer("I would just hold and wait") == 0
    # conservative keywords win within an answer
    assert fm.score_risk_answer("I'd buy more but honestly I'd be scared") == -1


def test_risk_profile_mapping():
    agg = fm.risk_profile_from_answers(["top up more", "buy the dip", "hold"])
    assert agg["risk_profile"] == "aggressive"
    assert agg["equity_band"] == 0.75
    assert agg["expected_return"] == 0.13

    cons = fm.risk_profile_from_answers(["exit everything", "move to FD"])
    assert cons["risk_profile"] == "conservative"
    assert cons["equity_band"] == 0.30

    # Mixed signals (one aggressive + one conservative) cancel → balanced.
    bal = fm.risk_profile_from_answers(["top up", "protect capital"])
    assert bal["risk_profile"] == "balanced"
    assert bal["expected_return"] == 0.11

    # Single tilt is enough under the 2-question threshold (±1).
    tilt = fm.risk_profile_from_answers(["hold steady", "maximize returns"])
    assert tilt["risk_profile"] == "aggressive"


def test_horizon_bucket():
    assert fm.horizon_bucket(1) == "short"
    assert fm.horizon_bucket(3) == "short"
    assert fm.horizon_bucket(4) == "medium"
    assert fm.horizon_bucket(7) == "medium"
    assert fm.horizon_bucket(8) == "long"
    assert fm.horizon_bucket(25) == "long"


def test_build_phases_short():
    phases = fm.build_phases("short", 3, 10_000)
    assert len(phases) == 1
    assert phases[0]["duration_years"] == 3
    assert phases[0]["allocation"]["debt"] == 0.95
    # Equity allocation is 0 → no equity funds in this phase
    assert all(f["bucket"] != "equity" for f in phases[0]["funds"])


def test_build_phases_medium_durations_sum_to_horizon():
    for years in (4, 5, 6, 7):
        phases = fm.build_phases("medium", years, 20_000)
        assert len(phases) == 2
        assert sum(p["duration_years"] for p in phases) == years


def test_build_phases_long_glides_equity_down():
    phases = fm.build_phases("long", 25, 30_000)
    assert len(phases) == 3
    assert sum(p["duration_years"] for p in phases) == 25
    # Equity share should decrease monotonically across phases (glide-down)
    eq = [p["allocation"]["equity"] for p in phases]
    assert eq[0] > eq[1] > eq[2]
    # All phases have at least one fund
    assert all(p["funds"] for p in phases)
