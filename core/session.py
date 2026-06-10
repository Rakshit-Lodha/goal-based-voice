"""In-memory session state (one call at a time) + progress checklist + next_step logic."""

from dataclasses import dataclass, field


@dataclass
class Goal:
    name: str
    target_amount_today: float
    horizon_years: int
    priority: int  # 1 = highest
    inflated_target: float | None = None
    projected_from_existing: float | None = None
    required_sip: float | None = None
    funded: bool = True


@dataclass
class SessionState:
    name: str | None = None
    monthly_income: float | None = None
    monthly_expenses: float | None = None
    monthly_emi: float | None = None
    portfolio: dict | None = None
    ratios: dict | None = None
    risk_profile: str | None = None
    risk_answers: list[str] = field(default_factory=list)
    goals: list[Goal] = field(default_factory=list)
    gap_result: dict | None = None
    proposed_portfolio: dict | None = None
    plan_pdf_path: str | None = None
    # fraction of the existing corpus not yet earmarked to a goal (waterfall)
    corpus_fraction_remaining: float = 1.0


STATE = SessionState()


def reset():
    # mutate in place: other modules hold a reference to STATE
    STATE.__dict__.update(SessionState().__dict__)
    return STATE


def get_goal(name: str) -> Goal | None:
    name = name.strip().lower()
    for g in STATE.goals:
        if g.name.strip().lower() == name:
            return g
    return None


def progress() -> dict:
    s = STATE
    gaps_done = bool(s.goals) and all(g.required_sip is not None for g in s.goals if g.funded)
    return {
        "portfolio": "done" if s.portfolio else "pending",
        "finances": "done" if s.ratios else "pending",
        "goals": "done" if len(s.goals) >= 2 else "pending",
        "risk": "done" if s.risk_profile else "pending",
        "gap": "done" if gaps_done else "pending",
        "portfolio_plan": "done" if s.proposed_portfolio else "pending",
        "pdf": "done" if s.plan_pdf_path else "pending",
    }


def next_step() -> str:
    s = STATE
    if not s.portfolio:
        return "Call get_existing_portfolio with the caller's name and narrate what you find."
    if not s.ratios:
        return ("Collect monthly income, expenses and any EMIs conversationally, "
                "then call compute_financial_ratios.")
    if len(s.goals) < 2:
        return ("Collect the user's goals (2-3 max). For each, anchor a today-cost and a year, "
                "then call add_goal.")
    if not s.risk_profile:
        return ("Ask 2-3 behavioral risk scenario questions (e.g. market drops 20% — top up, "
                "hold, or exit?), then call assess_risk_profile with the verbatim answers.")
    pending_gap = next((g for g in s.goals if g.funded and g.required_sip is None), None)
    if pending_gap:
        return (f"For goal '{pending_gap.name}': call project_existing_corpus, then "
                f"compute_gap_and_sip. Present the gap honestly.")
    if not s.proposed_portfolio:
        return ("If the total SIP felt tight or unaffordable, negotiate with reprioritize. "
                "Otherwise call build_portfolio with the agreed monthly SIP.")
    if not s.plan_pdf_path:
        return "Call generate_plan_pdf, then summarize 3 action items and close warmly."
    return "Plan is done. Summarize the 3 action items and say a warm goodbye."


def tool_response(payload: dict, narration_hint: str) -> dict:
    """Shared wrapper: every tool result re-anchors the LLM with progress + next_step."""
    return {
        **payload,
        "narration_hint": narration_hint,
        "progress": progress(),
        "next_step": next_step(),
    }


def missing(what: str, ask: str) -> dict:
    """Guard-rail response when a tool is called before its prerequisites exist."""
    return {
        "error": f"missing: {what}",
        "instruction": f"You haven't collected {what} yet. {ask}",
        "progress": progress(),
        "next_step": next_step(),
    }
