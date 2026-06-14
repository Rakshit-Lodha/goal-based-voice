from core.session import STATE, next_step, progress, reset


def _set_ready_for_financial_confirmation():
    reset()
    STATE.risk_profile = "balanced"
    STATE.family = {"spouse_age": None, "children": [], "dependents_count": 0}
    STATE.portfolio = {
        "total_value": 1_800_000,
        "total_monthly_sip": 12_000,
        "equity_value": 1_360_000,
        "debt_value": 440_000,
    }
    STATE.aa_assets = {"epf": 450_000, "nps": 50_000, "stocks": 500_000}
    STATE.monthly_income = 150_000
    STATE.monthly_expenses = 70_000
    STATE.monthly_emi = 25_000
    STATE.expense_breakdown = {
        "investments": 20_000,
        "household_expenses": 30_000,
        "utilities": 8_000,
        "entertainment": 12_000,
        "emis": 25_000,
    }
    STATE.ratios = {"idle_surplus": 43_000}


def test_next_step_blocks_goals_until_financial_snapshot_confirmed():
    _set_ready_for_financial_confirmation()

    assert progress()["finances"] == "pending"
    assert "Do not move to goals yet" in next_step()
    assert "PPF" in next_step()
    assert "US stocks" in next_step()
    assert "international stocks" in next_step()


def test_next_step_moves_to_goals_after_financial_snapshot_confirmed():
    _set_ready_for_financial_confirmation()
    STATE.financial_snapshot_confirmed = True

    assert progress()["finances"] == "done"
    assert next_step().startswith("Before goals, briefly review the MF Central portfolio")
    assert "Then discuss goals" in next_step()
