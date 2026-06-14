import pytest

from core import finmath as fm


def test_short_term_portfolio_has_debt_heavy_gold_hedge():
    """Short-term goals use one debt-heavy phase with a five percent gold hedge."""
    phases = fm.build_phases("short", 3, 20_000)

    assert len(phases) == 1
    assert phases[0]["allocation"] == {"equity": 0.0, "debt": 0.95, "gold": 0.05}
    assert any(f["fund"] == "Gold ETF Fund of Fund" for f in phases[0]["funds"])


def test_medium_term_portfolio_glides_to_more_debt_and_keeps_gold():
    """Medium-term goals use two phases, reduce equity, and keep gold exposure in both phases."""
    phases = fm.build_phases("medium", 6, 25_000)

    assert len(phases) == 2
    assert phases[0]["allocation"]["equity"] > phases[1]["allocation"]["equity"]
    assert [p["allocation"]["gold"] for p in phases] == [0.10, 0.05]
    assert all(any(f["bucket"] == "gold" for f in p["funds"]) for p in phases)


def test_long_term_portfolio_has_three_phase_equity_glide_down_with_gold():
    """Long-term goals use three phases, glide equity down, and allocate to gold in every phase."""
    phases = fm.build_phases("long", 25, 30_000)

    assert len(phases) == 3
    assert sum(p["duration_years"] for p in phases) == 25
    assert [p["allocation"]["equity"] for p in phases] == [0.80, 0.50, 0.20]
    assert [p["allocation"]["gold"] for p in phases] == [0.05, 0.10, 0.10]
    assert all(any(f["fund"] == "Gold ETF Fund of Fund" for f in p["funds"]) for p in phases)


def test_every_phase_allocation_sums_to_one():
    """Every deterministic phase allocation must sum to one hundred percent."""
    for bucket, years in (("short", 2), ("medium", 5), ("long", 12)):
        for phase in fm.build_phases(bucket, years, 10_000):
            assert sum(phase["allocation"].values()) == pytest.approx(1.0)
