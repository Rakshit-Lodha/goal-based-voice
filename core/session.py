"""In-memory session state (one call at a time) + progress checklist + next_step logic."""

import os
from dataclasses import asdict, dataclass, field

# Demo persona — caller is treated as already KYC-verified, so Maya never asks
# for name or age. Both prompts.py and reset() read from these constants.
KYC_NAME = "Rakshit"
KYC_AGE = 28


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
    age: int | None = None
    monthly_income: float | None = None
    monthly_expenses: float | None = None
    monthly_emi: float | None = None
    expense_breakdown: dict | None = None
    portfolio: dict | None = None
    ratios: dict | None = None
    risk_profile: str | None = None
    risk_answers: list[str] = field(default_factory=list)
    # Family captured in stage 2: {spouse_age, children: [{age}], dependents_count}.
    family: dict | None = None
    # AA-pulled non-MF holdings: {epf, nps, stocks, ...}. Narrated, not yet in gap math.
    aa_assets: dict | None = None
    # True only after the user has accepted AA-derived cash flow/assets and answered
    # the additional-investments check.
    financial_snapshot_confirmed: bool = False
    # Voice-added extras (PPF, FDs, gold, real estate): list of {name, asset_type, value}.
    additional_assets: list = field(default_factory=list)
    goals: list[Goal] = field(default_factory=list)
    gap_result: dict | None = None
    # Per-goal phase plans keyed by goal name (see finmath.build_phases).
    proposed_portfolios: dict = field(default_factory=dict)
    plan_pdf_path: str | None = None
    # fraction of the existing corpus not yet earmarked to a goal (waterfall)
    corpus_fraction_remaining: float = 1.0


STATE = SessionState()


def reset():
    # mutate in place: other modules hold a reference to STATE
    STATE.__dict__.update(SessionState().__dict__)
    STATE.name = KYC_NAME
    STATE.age = KYC_AGE
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
    funded = [g for g in s.goals if g.funded and (g.required_sip or 0) > 0]
    plan_done = bool(funded) and all(g.name in s.proposed_portfolios for g in funded)
    return {
        "risk": "done" if s.risk_profile else "pending",
        "family": "done" if s.family else "pending",
        "mfc": "done" if s.portfolio else "pending",
        "aa": "done" if s.aa_assets else "pending",
        "finances": "done" if s.ratios and s.financial_snapshot_confirmed else "pending",
        "goals": "done" if len(s.goals) >= 1 else "pending",
        "gap": "done" if gaps_done else "pending",
        "portfolio_plan": "done" if plan_done else "pending",
        "pdf": "done" if s.plan_pdf_path else "pending",
    }


def next_step() -> str:
    s = STATE
    if not s.risk_profile:
        return ("Ask the two behavioral risk questions one at a time, then call "
                "assess_risk_profile with both verbatim answers.")
    if not s.family:
        return ("Ask about family — spouse age, each child's age, any other dependents. "
                "Then call add_family.")
    if not s.portfolio:
        return ("Do not call pull_mf_central yet unless the user has explicitly agreed. "
                "First explain that the next step is to pull all investment data, starting "
                "with MF Central: a SEBI-regulated consolidated mutual fund view from CAMS "
                "and KFintech, formerly Karvy. Explain that this helps analyze holdings, "
                "spot underperforming funds, and make the financial plan richer. Ask for "
                "permission to trigger the OTP. If they agree, say you are triggering the "
                "MF Central OTP now, then call pull_mf_central.")
    if not s.aa_assets:
        return ("Do not call pull_account_aggregator yet unless the user has explicitly agreed. "
                "First explain Finvu Account Aggregator: an RBI-regulated encrypted consent "
                "flow that can pull bank, EPF, NPS, stock, income and expense data. Explain "
                "that this helps analyze cash flow, stocks, EPF, income, expenses and makes "
                "the financial plan seamless and richer. Ask permission to trigger the OTP. "
                "If they agree, say you are triggering the Finvu OTP now, then call "
                "pull_account_aggregator.")
    if not s.financial_snapshot_confirmed:
        return ("Do not move to goals yet. First confirm the Account Aggregator snapshot: "
                "income, outflow, expense breakup, EMIs, EPF, NPS and stocks. If anything "
                "is wrong, call pull_account_aggregator again with corrections. Then ask "
                "whether the user wants to add any investments AA may not capture, especially "
                "PPF, FDs, gold, real estate, US stocks or international stocks. For each "
                "asset they mention, call add_manual_asset. Once the user explicitly says "
                "the data is correct and there are no more additions, call "
                "confirm_financial_snapshot.")
    # MF portfolio review is narrative-only — gated by portfolio + aa_assets both being set.
    if len(s.goals) < 1:
        return ("Before goals, briefly review the MF Central portfolio: explain that funds are "
                "judged by category suitability for the user's risk profile and by a score based "
                "on consistency versus category average plus downside protection. Mention good "
                "funds and underperformers from the portfolio payload without listing every fund. "
                "Then discuss goals (1-4 max). First explain the goal-planning framework: default "
                "primary goals are emergency fund and retirement because they create safety and "
                "long-term independence. Explain emergency fund as six months of runway for job "
                "loss, medical issues or any disruption, then call add_goal with no "
                "target_amount_today so the tool computes it. Also suggest retirement anchored "
                "to age 60 and child education if relevant.")
    pending_gap = next((g for g in s.goals if g.funded and g.required_sip is None), None)
    if pending_gap:
        return (f"For goal '{pending_gap.name}': call project_existing_corpus, then "
                f"compute_gap_and_sip. Present the gap honestly.")
    funded_goals = [g for g in s.goals if g.funded and (g.required_sip or 0) > 0]
    pending_plan = next((g for g in funded_goals if g.name not in s.proposed_portfolios), None)
    if pending_plan:
        if not s.proposed_portfolios:
            return ("If the total SIP felt tight, negotiate with reprioritize first. "
                    "Otherwise: in two or three sentences explain the phasing method "
                    "(short goals are one phase debt-heavy; medium two phases balanced; "
                    "long three phases equity-heavy with a glide-down to debt), then "
                    f"call build_goal_portfolio for '{pending_plan.name}'.")
        return f"Call build_goal_portfolio for '{pending_plan.name}' next."
    if not s.plan_pdf_path:
        return "Call generate_plan_pdf, then summarize 3 action items and close warmly."
    return "Plan is done. Summarize the 3 action items and say a warm goodbye."


def snapshot(last_event: str | None = None) -> dict:
    """JSON-serializable mirror of the whole session for the browser UI."""
    s = STATE
    return {
        "name": s.name,
        "age": s.age,
        "monthly_income": s.monthly_income,
        "monthly_expenses": s.monthly_expenses,
        "monthly_emi": s.monthly_emi,
        "expense_breakdown": s.expense_breakdown,
        "ratios": s.ratios,
        "risk_profile": s.risk_profile,
        "family": s.family,
        "aa_assets": s.aa_assets,
        "financial_snapshot_confirmed": s.financial_snapshot_confirmed,
        "additional_assets": s.additional_assets,
        "portfolio": s.portfolio,
        "goals": [asdict(g) for g in s.goals],
        "proposed_portfolios": s.proposed_portfolios,
        "plan_pdf_url": f"/output/{os.path.basename(s.plan_pdf_path)}" if s.plan_pdf_path else None,
        "progress": progress(),
        "last_event": last_event,
    }


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
