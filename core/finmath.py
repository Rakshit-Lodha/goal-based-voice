"""Pure deterministic financial math. No LLM, no I/O. All currency INR, rates as decimals."""

import math

# Annual growth assumptions for projecting existing holdings
EQUITY_GROWTH = 0.11
DEBT_GROWTH = 0.07

# Inflation by goal category
DEFAULT_INFLATION = 0.06
EDUCATION_INFLATION = 0.10
PROPERTY_INFLATION = 0.07

# Expected portfolio return by risk profile
EXPECTED_RETURN = {"conservative": 0.09, "balanced": 0.11, "aggressive": 0.13}

EQUITY_BAND = {"conservative": 0.30, "balanced": 0.55, "aggressive": 0.75}

# risk profile -> (equity, debt, gold) allocation
ALLOCATION = {
    "conservative": (0.30, 0.60, 0.10),
    "balanced": (0.55, 0.40, 0.05),
    "aggressive": (0.75, 0.20, 0.05),
}


def round_to_500(x: float) -> int:
    """Round to the nearest ₹500."""
    return int(round(x / 500.0) * 500)


def inflation_for_goal(goal_name: str) -> float:
    """Pick inflation rate from goal name keywords."""
    name = goal_name.lower()
    if any(k in name for k in ("education", "college", "school", "study", "studies", "mba", "degree")):
        return EDUCATION_INFLATION
    if any(k in name for k in ("house", "home", "property", "flat", "apartment", "plot")):
        return PROPERTY_INFLATION
    return DEFAULT_INFLATION


def inflate(amount_today: float, years: int, rate: float) -> float:
    """Future cost of a goal: amount × (1 + inflation)^years."""
    return amount_today * (1 + rate) ** years


def financial_ratios(monthly_income: float, monthly_expenses: float, monthly_emi: float = 0.0,
                     existing_monthly_sip: float = 0.0) -> dict:
    """Surplus, savings rate, DTI with qualitative bands, and idle surplus."""
    surplus = monthly_income - monthly_expenses - monthly_emi
    savings_rate = surplus / monthly_income if monthly_income else 0.0
    dti = monthly_emi / monthly_income if monthly_income else 0.0

    if savings_rate < 0.10:
        savings_band = "low"
    elif savings_rate <= 0.30:
        savings_band = "moderate"
    else:
        savings_band = "strong"

    if dti < 0.20:
        dti_band = "healthy"
    elif dti <= 0.40:
        dti_band = "moderate"
    else:
        dti_band = "stretched"

    return {
        "surplus": round(surplus),
        "savings_rate": round(savings_rate, 4),
        "savings_band": savings_band,
        "debt_to_income": round(dti, 4),
        "dti_band": dti_band,
        "idle_surplus": round(surplus - existing_monthly_sip),
    }


def lumpsum_fv(present_value: float, annual_rate: float, years: float) -> float:
    """FV of a lumpsum: PV × (1 + g)^n."""
    return present_value * (1 + annual_rate) ** years


def sip_fv(monthly_sip: float, annual_rate: float, years: float) -> float:
    """FV of a monthly SIP (annuity-due): sip × [((1+r)^(12n) − 1) / r] × (1+r), r = annual/12."""
    if monthly_sip <= 0:
        return 0.0
    r = annual_rate / 12
    m = 12 * years
    return monthly_sip * (((1 + r) ** m - 1) / r) * (1 + r)


def required_sip(target: float, annual_rate: float, years: float) -> float:
    """Monthly SIP needed to reach target: target × r / (((1+r)^(12n) − 1) × (1+r))."""
    if target <= 0:
        return 0.0
    r = annual_rate / 12
    m = 12 * years
    return target * r / ((((1 + r) ** m) - 1) * (1 + r))


def years_to_target(monthly_sip: float, target: float, annual_rate: float) -> float:
    """Solve the SIP FV formula for n (in years, 1 decimal) given a fixed SIP."""
    if target <= 0:
        return 0.0
    if monthly_sip <= 0:
        return math.inf
    r = annual_rate / 12
    months = math.log(target * r / (monthly_sip * (1 + r)) + 1) / math.log(1 + r)
    return round(months / 12, 1)


def blended_growth(equity_value: float, debt_value: float) -> float:
    """Value-weighted growth rate across equity and debt holdings."""
    total = equity_value + debt_value
    if total <= 0:
        return DEBT_GROWTH
    return (equity_value * EQUITY_GROWTH + debt_value * DEBT_GROWTH) / total


def affordability(required: float, idle_surplus: float) -> str:
    """comfortable (≤70% of surplus) / tight (70–100%) / unaffordable (>100%)."""
    if idle_surplus <= 0:
        return "unaffordable"
    ratio = required / idle_surplus
    if ratio <= 0.70:
        return "comfortable"
    if ratio <= 1.0:
        return "tight"
    return "unaffordable"


# Deterministic risk scoring. Each free-text answer scores -1 (conservative),
# 0 (balanced), or +1 (aggressive) by keyword match; conservative keywords win
# ties within an answer. Total across answers maps to a profile:
#   total >= 2 -> aggressive, total <= -2 -> conservative, else balanced.
_AGGRESSIVE_KW = ("top up", "topup", "buy more", "invest more", "add more", "buy the dip",
                  "opportunity", "double down", "lump sum", "buy")
_CONSERVATIVE_KW = ("exit", "sell", "withdraw", "redeem", "stop", "panic", "scared",
                    "afraid", "worried", "worry", "fd", "fixed deposit", "safe", "pull out")


def score_risk_answer(answer: str) -> int:
    a = answer.lower()
    if any(k in a for k in _CONSERVATIVE_KW):
        return -1
    if any(k in a for k in _AGGRESSIVE_KW):
        return 1
    return 0


def risk_profile_from_answers(answers: list[str]) -> dict:
    total = sum(score_risk_answer(a) for a in answers)
    if total >= 2:
        profile = "aggressive"
    elif total <= -2:
        profile = "conservative"
    else:
        profile = "balanced"
    return {
        "risk_profile": profile,
        "score": total,
        "equity_band": EQUITY_BAND[profile],
        "expected_return": EXPECTED_RETURN[profile],
    }
