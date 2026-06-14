"""Stubbed "MF Central" portfolio fixtures keyed by caller first name (lowercase)."""

# rating 1-5; rating <= 2 is flagged "underperformer"
PORTFOLIOS = {
    # ~₹18L across 6 funds, 2 poor performers, ₹12K existing SIPs
    "rohan": {
        "holdings": [
            {"fund": "Bluechip Large Cap Fund", "category": "large cap", "type": "equity", "current_value": 520_000, "monthly_sip": 5_000, "rating": 4},
            {"fund": "Flexi Cap Opportunities Fund", "category": "flexi cap", "type": "equity", "current_value": 410_000, "monthly_sip": 4_000, "rating": 4},
            {"fund": "Midcap Momentum Fund", "category": "mid cap", "type": "equity", "current_value": 280_000, "monthly_sip": 0, "rating": 2},
            {"fund": "Thematic Infra Fund", "category": "thematic", "type": "equity", "current_value": 150_000, "monthly_sip": 0, "rating": 1},
            {"fund": "Short Duration Debt Fund", "category": "short duration debt", "type": "debt", "current_value": 290_000, "monthly_sip": 3_000, "rating": 4},
            {"fund": "Liquid Fund", "category": "liquid", "type": "debt", "current_value": 150_000, "monthly_sip": 0, "rating": 3},
        ],
    },
    # smaller, cleaner portfolio
    "priya": {
        "holdings": [
            {"fund": "Nifty 50 Index Fund", "category": "large cap index", "type": "equity", "current_value": 240_000, "monthly_sip": 5_000, "rating": 4},
            {"fund": "Aggressive Hybrid Fund", "category": "aggressive hybrid", "type": "equity", "current_value": 120_000, "monthly_sip": 0, "rating": 2},
            {"fund": "Corporate Bond Fund", "category": "corporate bond", "type": "debt", "current_value": 90_000, "monthly_sip": 2_000, "rating": 4},
        ],
    },
}

DEFAULT_PERSONA = "rohan"


def lookup(name: str) -> dict:
    """Return the fixture for this caller, defaulting to the main demo persona."""
    key = (name or "").strip().lower().split(" ")[0]
    data = PORTFOLIOS.get(key, PORTFOLIOS[DEFAULT_PERSONA])
    holdings = [
        {**h, "flag": "underperformer" if h["rating"] <= 2 else None}
        for h in data["holdings"]
    ]
    return {
        "holdings": holdings,
        "total_value": sum(h["current_value"] for h in holdings),
        "total_monthly_sip": sum(h["monthly_sip"] for h in holdings),
        "equity_value": sum(h["current_value"] for h in holdings if h["type"] == "equity"),
        "debt_value": sum(h["current_value"] for h in holdings if h["type"] == "debt"),
        "underperformers": [h["fund"] for h in holdings if h["flag"]],
    }
