"""Tool schemas + handlers. Tools own ALL math; the LLM only converses.

Every handler returns through session.tool_response() so the LLM is re-anchored
with narration_hint / progress / next_step on every call. Guard rails return an
{"error", "instruction"} payload instead of raising.
"""

import json
import math

from loguru import logger

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import FunctionCallParams

from core import finmath as fm
from core import consent, plan_pdf, portfolio_data, ui_bus
from core.session import STATE, Goal, get_goal, missing, snapshot, tool_response


def _pct(x: float) -> str:
    return f"{x * 100:.0f} percent"


def _fund_review(holding: dict, risk_profile: str | None) -> dict:
    category = holding.get("category") or holding["type"]
    rating = int(holding.get("rating") or 0)
    category_suitable = category != "thematic"
    score_good = rating >= 3

    reasons = []
    if category_suitable:
        reasons.append(f"the {category} category fits a {risk_profile or 'balanced'} risk profile")
    else:
        reasons.append("thematic funds are too concentrated for this risk-profile-led plan")
    if score_good:
        reasons.append("the fund score is acceptable on consistency versus category average and downside protection")
    else:
        reasons.append("the fund score is weak on consistency versus category average or downside protection")

    return {
        "fund": holding["fund"],
        "category": category,
        "rating": rating,
        "category_suitable": category_suitable,
        "score_good": score_good,
        "status": "good" if category_suitable and score_good else "review",
        "reason": "; ".join(reasons),
    }


# ---------------------------------------------------------------- handlers

async def pull_mf_central(args: dict) -> dict:
    """Stage 3a: fetch the caller's mutual fund portfolio from MF Central (mocked)."""
    if not args.get("user_confirmed_consent"):
        return missing("MF Central consent",
                       "Explain why MF Central is needed, ask permission to trigger the OTP, and only call this after the user agrees.")
    otp = await consent.request_otp("MF Central")
    if str(otp).replace(" ", "") != "1234":
        return missing("the MF Central OTP",
                       "Tell the user the OTP did not match, then call pull_mf_central again so they can retry.")
    STATE.portfolio = portfolio_data.lookup(STATE.name or "client")
    p = STATE.portfolio
    for edit in args.get("holding_edits") or []:
        fund = (edit.get("fund") or "").strip().lower()
        holding = next((h for h in p["holdings"] if h["fund"].strip().lower() == fund), None)
        if not holding:
            continue
        if edit.get("current_value") is not None:
            holding["current_value"] = float(edit["current_value"])
        if edit.get("monthly_sip") is not None:
            holding["monthly_sip"] = float(edit["monthly_sip"])
    if args.get("holding_edits"):
        p["total_value"] = sum(h["current_value"] for h in p["holdings"])
        p["total_monthly_sip"] = sum(h["monthly_sip"] for h in p["holdings"])
        p["equity_value"] = sum(h["current_value"] for h in p["holdings"] if h["type"] == "equity")
        p["debt_value"] = sum(h["current_value"] for h in p["holdings"] if h["type"] == "debt")
    reviews = [_fund_review(h, STATE.risk_profile) for h in p["holdings"]]
    p["fund_reviews"] = reviews
    p["good_funds"] = [r["fund"] for r in reviews if r["status"] == "good"]
    p["underperformers"] = [r["fund"] for r in reviews if r["status"] != "good"]
    p["review_methodology"] = (
        "We judge each fund on two things: whether its category suits the user's "
        "risk profile, and a fund score based on consistency versus category average "
        "plus downside protection."
    )
    under = p["underperformers"]
    hint = (f"MF Central is back. Portfolio of {fm.round_to_500(p['total_value']) / 1e5:.0f} "
            f"lakhs across {len(p['holdings'])} funds with {p['total_monthly_sip']} rupees of "
            f"monthly SIPs. Explain that fund review uses category suitability for the "
            f"user's {STATE.risk_profile or 'risk'} profile plus a score based on consistency "
            f"versus category average and downside protection. ")
    if under:
        reasons = "; ".join(f"{r['fund']}: {r['reason']}" for r in reviews if r["status"] != "good")
        hint += (f"{len(under)} of {len(p['holdings'])} funds need review: "
                 f"{', '.join(under)}. Use these reasons briefly: {reasons}.")
    else:
        hint += "No red flags — a clean portfolio."
    return tool_response(p, hint)


async def pull_account_aggregator(args: dict) -> dict:
    """Stage 3b: AA (Finvu) pull — income/expense/EMI plus other-asset snapshot."""
    if not STATE.portfolio:
        return missing("the MF Central pull",
                       "Call pull_mf_central first so existing SIPs feed into idle surplus.")
    if not STATE.aa_assets:
        if not args.get("user_confirmed_consent"):
            return missing("Account Aggregator consent",
                           "Explain what Account Aggregator is, what data it pulls and why it helps the plan. Ask permission to trigger the OTP, and only call this after the user agrees.")
        otp = await consent.request_otp("Finvu Account Aggregator")
        if str(otp).replace(" ", "") != "1234":
            return missing("the Account Aggregator OTP",
                           "Tell the user the OTP did not match, then call pull_account_aggregator again so they can retry.")

    previous_breakdown = STATE.expense_breakdown or {}
    breakdown = {
        "investments": float(args.get("investments") if args.get("investments") is not None
                             else previous_breakdown.get("investments", 20_000)),
        "household_expenses": float(args.get("household_expenses") if args.get("household_expenses") is not None
                                    else previous_breakdown.get("household_expenses", 30_000)),
        "utilities": float(args.get("utilities") if args.get("utilities") is not None
                           else previous_breakdown.get("utilities", 8_000)),
        "entertainment": float(args.get("entertainment") if args.get("entertainment") is not None
                               else previous_breakdown.get("entertainment", 12_000)),
    }
    STATE.monthly_income = float(args.get("monthly_income") if args.get("monthly_income") is not None
                                 else STATE.monthly_income or 150_000)
    STATE.monthly_emi = float(args.get("monthly_emi") if args.get("monthly_emi") is not None
                              else STATE.monthly_emi or 25_000)
    non_emi_total = sum(breakdown.values())
    STATE.monthly_expenses = float(args.get("monthly_expenses") if args.get("monthly_expenses") is not None
                                   else non_emi_total)
    STATE.expense_breakdown = {**breakdown, "emis": STATE.monthly_emi}
    previous_assets = STATE.aa_assets or {}
    STATE.aa_assets = {
        "epf": float(args.get("epf") if args.get("epf") is not None
                     else previous_assets.get("epf", 450_000)),
        "nps": float(args.get("nps") if args.get("nps") is not None
                     else previous_assets.get("nps", 50_000)),
        "stocks": float(args.get("stocks") if args.get("stocks") is not None
                        else previous_assets.get("stocks", 500_000)),
    }
    existing_sip = STATE.portfolio["total_monthly_sip"]
    STATE.ratios = fm.financial_ratios(
        STATE.monthly_income, STATE.monthly_expenses, STATE.monthly_emi, existing_sip)
    r = STATE.ratios
    aa = STATE.aa_assets
    total_outflow = STATE.monthly_expenses + STATE.monthly_emi
    hint = (f"Finvu is back. Say you looked at the last three months of bank data. "
            f"Average monthly income is {STATE.monthly_income} rupees. Average monthly outflow "
            f"is {total_outflow} rupees: investments {breakdown['investments']}, EMIs "
            f"{STATE.monthly_emi}, household {breakdown['household_expenses']}, utilities "
            f"{breakdown['utilities']}, entertainment {breakdown['entertainment']}. "
            f"Also say the savings rate is {_pct(r['savings_rate'])}, which is {r['savings_band']}; "
            f"the EMI-to-income ratio is {_pct(r['debt_to_income'])}, which is {r['dti_band']}. "
            f"Ask if this looks correct. If not, ask for the corrected value and call "
            f"pull_account_aggregator again with that correction; do not ask for OTP again. "
            f"Also mention EPF {aa['epf']}, NPS {aa['nps']}, stocks {aa['stocks']}.")
    return tool_response({"ratios": r, "aa_assets": aa,
                          "monthly_income": STATE.monthly_income,
                          "monthly_expenses": STATE.monthly_expenses,
                          "monthly_emi": STATE.monthly_emi,
                          "expense_breakdown": STATE.expense_breakdown}, hint)


async def add_family(args: dict) -> dict:
    """Stage 2: capture spouse age, children (with ages), and other dependents."""
    spouse_age = args.get("spouse_age")
    children = args.get("children") or []  # list of {"age": int}
    dependents_count = int(args.get("dependents_count") or 0)
    STATE.family = {
        "spouse_age": int(spouse_age) if spouse_age is not None else None,
        "children": [{"age": int(c["age"])} for c in children if "age" in c],
        "dependents_count": dependents_count,
    }
    parts = []
    if STATE.family["spouse_age"] is not None:
        parts.append(f"spouse aged {STATE.family['spouse_age']}")
    if STATE.family["children"]:
        ages = ", ".join(str(c["age"]) for c in STATE.family["children"])
        parts.append(f"{len(STATE.family['children'])} child(ren) aged {ages}")
    if dependents_count:
        parts.append(f"{dependents_count} other dependent(s)")
    summary = "; ".join(parts) or "no immediate dependents"
    hint = (f"Family captured — {summary}. Keep this in mind when goals come up: a young child "
            f"suggests an education goal in 18-minus-age years; the caller's own age plus "
            f"retirement age suggests a retirement goal.")
    return tool_response(STATE.family, hint)


async def add_manual_asset(args: dict) -> dict:
    """Stage 3c (optional): voice-added extras like PPF, FDs, gold, real estate."""
    entry = {
        "name": args["name"],
        "asset_type": args.get("asset_type") or "other",
        "value": float(args["value"]),
    }
    STATE.additional_assets.append(entry)
    total = sum(a["value"] for a in STATE.additional_assets)
    hint = (f"Added {entry['name']} worth {entry['value']:.0f} rupees. "
            f"Total manual extras now {total:.0f} rupees across "
            f"{len(STATE.additional_assets)} item(s). Ask if there is anything else.")
    return tool_response({"added": entry, "additional_assets": STATE.additional_assets}, hint)


async def confirm_financial_snapshot(args: dict) -> dict:
    """Gate before goals: user accepted AA data and answered manual additions."""
    if not STATE.aa_assets or not STATE.ratios:
        return missing("the Account Aggregator pull",
                       "Call pull_account_aggregator first so there is a financial snapshot to confirm.")
    if not args.get("user_confirmed_financial_data"):
        return missing("explicit confirmation of the Account Aggregator data",
                       "Ask whether the income, outflow, expense breakup, EMIs, EPF, NPS and stocks look correct.")
    if not args.get("user_answered_additional_assets"):
        return missing("the additional-investments answer",
                       "Ask whether they want to add PPF, FDs, gold, real estate, US stocks or international stocks before goals.")

    STATE.financial_snapshot_confirmed = True
    hint = ("Financial snapshot confirmed. The user accepted the AA-derived cash flow "
            "and holdings, and has answered the additional-investments check. Before goals, "
            "review the MF Central portfolio: explain category suitability for the user's "
            "risk profile and fund score based on consistency versus category average plus "
            "downside protection, then mention the good funds and underperformers briefly.")
    return tool_response({
        "financial_snapshot_confirmed": True,
        "additional_assets": STATE.additional_assets,
    }, hint)


async def assess_risk_profile(args: dict) -> dict:
    answers = args["answers"]
    if not answers or len(answers) < 2:
        return missing("at least 2 risk scenario answers",
                       "Ask another behavioral scenario question first.")
    STATE.risk_answers = answers
    result = fm.risk_profile_from_answers(answers)
    STATE.risk_profile = result["risk_profile"]
    hint = (f"The user comes out {result['risk_profile']}: roughly "
            f"{result['equity_band'] * 100:.0f} percent equity suits them, and we'll plan "
            f"with {result['expected_return'] * 100:.0f} percent expected returns.")
    return tool_response(result, hint)


async def add_goal(args: dict) -> dict:
    if len(STATE.goals) >= 4:
        return missing("room for another goal",
                       "Four goals are already captured — that's the maximum. Move on.")
    name = args["name"]
    horizon = int(args.get("horizon_years") or 1)
    if horizon < 1:
        return missing("a valid horizon", "Ask for a target year at least 1 year away.")
    if args.get("target_amount_today") is None:
        if "emergency" not in name.lower():
            return missing("a goal amount",
                           "Ask for today's cost for this goal, unless it is the emergency fund.")
        if STATE.monthly_expenses is None or STATE.monthly_emi is None:
            return missing("the monthly expense outflow",
                           "Call pull_account_aggregator first so the emergency fund can use six months of expenses.")
        amount = (STATE.monthly_expenses + STATE.monthly_emi) * 6
    else:
        amount = float(args["target_amount_today"])
    inflation = 0.0 if "emergency" in name.lower() else fm.inflation_for_goal(name)
    goal = Goal(
        name=name,
        target_amount_today=amount,
        horizon_years=horizon,
        priority=int(args["priority"]),
        inflated_target=round(fm.inflate(amount, horizon, inflation)),
    )
    STATE.goals.append(goal)
    if "emergency" in name.lower():
        hint = (f"Emergency fund captured at {amount:.0f} rupees — six months of the "
                f"user's confirmed monthly outflow. Explain it as the first safety goal "
                f"before long-term investing.")
    else:
        hint = (f"Captured. With {inflation * 100:.0f} percent inflation, today's "
                f"{amount / 1e5:.0f} lakh becomes about {goal.inflated_target / 1e5:.0f} lakhs "
                f"in {horizon} years — react to that jump.")
    return tool_response({
        "goal": name,
        "inflated_target": goal.inflated_target,
        "inflation_used": inflation,
        "goals_captured": len(STATE.goals),
    }, hint)


async def project_existing_corpus(args: dict) -> dict:
    if not STATE.portfolio:
        return missing("the existing portfolio",
                       "Call pull_mf_central first.")
    goal = get_goal(args["goal_name"])
    if not goal:
        return missing(f"a goal named '{args['goal_name']}'",
                       "Add the goal with add_goal first, or use the exact goal name.")
    p = STATE.portfolio
    g_rate = fm.blended_growth(p["equity_value"], p["debt_value"])
    n = goal.horizon_years
    fv_total = fm.lumpsum_fv(p["total_value"], g_rate, n) + fm.sip_fv(p["total_monthly_sip"], g_rate, n)
    # waterfall: only the un-earmarked fraction of the corpus is available to this goal
    available = fv_total * STATE.corpus_fraction_remaining
    earmarked = min(available, goal.inflated_target)
    if fv_total > 0:
        STATE.corpus_fraction_remaining = max(0.0, STATE.corpus_fraction_remaining - earmarked / fv_total)
    goal.projected_from_existing = round(earmarked)
    coverage = earmarked / goal.inflated_target if goal.inflated_target else 0
    hint = (f"Existing investments, grown at {g_rate * 100:.1f} percent blended, cover about "
            f"{coverage * 100:.0f} percent of the {goal.name} goal.")
    return tool_response({
        "goal": goal.name,
        "projected_from_existing": goal.projected_from_existing,
        "inflated_target": goal.inflated_target,
        "coverage_pct": round(coverage * 100, 1),
        "blended_growth_used": round(g_rate, 4),
    }, hint)


async def compute_gap_and_sip(args: dict) -> dict:
    if not STATE.risk_profile:
        return missing("the risk profile",
                       "Ask the behavioral risk questions and call assess_risk_profile first.")
    if not STATE.ratios:
        return missing("the Account Aggregator pull",
                       "Call pull_account_aggregator first — it sets income, expenses and EMIs.")
    goal = get_goal(args["goal_name"])
    if not goal:
        return missing(f"a goal named '{args['goal_name']}'", "Add the goal with add_goal first.")
    if goal.projected_from_existing is None:
        return missing(f"the projection for '{goal.name}'",
                       "Call project_existing_corpus for this goal first.")

    rate = float(args.get("expected_return") or fm.EXPECTED_RETURN[STATE.risk_profile])
    gap = max(0.0, goal.inflated_target - goal.projected_from_existing)
    goal.required_sip = fm.round_to_500(fm.required_sip(gap, rate, goal.horizon_years))
    idle = STATE.ratios["idle_surplus"]
    total_sip = sum(g.required_sip or 0 for g in STATE.goals if g.funded)
    afford = fm.affordability(total_sip, idle)

    STATE.gap_result = {
        "goal": goal.name,
        "gap": round(gap),
        "required_sip": goal.required_sip,
        "expected_return_used": rate,
        "total_required_sip_all_goals": total_sip,
        "idle_surplus": idle,
        "affordability": afford,
    }
    hint = (f"For {goal.name} the gap needs {goal.required_sip} rupees a month. Across all goals "
            f"so far that's {total_sip} rupees against an idle surplus of {idle} — {afford}.")
    return tool_response(STATE.gap_result, hint)


async def reprioritize(args: dict) -> dict:
    funded_goals = [g for g in sorted(STATE.goals, key=lambda g: g.priority) if g.required_sip is not None]
    if not funded_goals:
        return missing("computed SIPs for the goals",
                       "Run project_existing_corpus and compute_gap_and_sip for each goal first.")
    budget = float(args["max_affordable_sip"])
    rate = fm.EXPECTED_RETURN[STATE.risk_profile or "balanced"]
    remaining = budget
    table = []
    for g in funded_goals:
        need = g.required_sip or 0
        if need <= remaining:
            remaining -= need
            g.funded = True
            table.append({"goal": g.name, "priority": g.priority, "assigned_sip": need,
                          "status": "fully funded"})
        elif remaining >= 500:
            assigned = fm.round_to_500(remaining)
            assigned = min(assigned, int(remaining // 500) * 500) or 500
            gap = max(0.0, g.inflated_target - (g.projected_from_existing or 0))
            achieved = fm.sip_fv(assigned, rate, g.horizon_years)
            shortfall = max(0.0, gap - achieved)
            extended = fm.years_to_target(assigned, gap, rate)
            g.funded = True
            g.required_sip = assigned
            remaining = 0
            table.append({
                "goal": g.name, "priority": g.priority, "assigned_sip": assigned,
                "status": "partially funded",
                "shortfall_at_horizon": round(shortfall),
                "shortfall_pct": round(shortfall / g.inflated_target * 100, 1),
                "or_extend_horizon_to_years": None if math.isinf(extended) else extended,
                "original_horizon_years": g.horizon_years,
            })
        else:
            g.funded = False
            g.required_sip = 0
            table.append({"goal": g.name, "priority": g.priority, "assigned_sip": 0,
                          "status": "parked — no budget left"})
    partial = next((r for r in table if r["status"] == "partially funded"), None)
    if partial:
        hint = (f"At {budget:.0f} rupees a month, {partial['goal']} falls short by about "
                f"{partial['shortfall_pct']} percent — or it moves out to "
                f"{partial['or_extend_horizon_to_years']} years. Offer the trade-off and let them choose.")
    else:
        parked = [r["goal"] for r in table if r["assigned_sip"] == 0]
        hint = (f"At this budget, {', '.join(parked)} gets parked." if parked
                else "All goals fit within this budget.")
    return tool_response({"max_affordable_sip": budget, "goals": table}, hint)


async def build_goal_portfolio(args: dict) -> dict:
    if not STATE.risk_profile:
        return missing("the risk profile", "Call assess_risk_profile first.")
    goal = get_goal(args["goal_name"])
    if not goal:
        return missing(f"a goal named '{args['goal_name']}'",
                       "Use the exact goal name; add it with add_goal first if missing.")
    if not goal.funded or not goal.required_sip:
        return missing(f"a funded SIP for '{goal.name}'",
                       "Run compute_gap_and_sip (and reprioritize if needed) for this goal first.")

    bucket = fm.horizon_bucket(goal.horizon_years)
    phases = fm.build_phases(bucket, goal.horizon_years, goal.required_sip)

    STATE.proposed_portfolios[goal.name] = {
        "goal": goal.name,
        "horizon_bucket": bucket,
        "horizon_years": goal.horizon_years,
        "monthly_sip": goal.required_sip,
        "phases": phases,
        "current_phase": phases[0],
        "selection_basis": ("This goal-based portfolio is built from the user's risk profile and "
                            "goal horizon, using top category funds from each required category "
                            "to balance risk and return."),
    }

    if bucket == "long":
        hint = (f"{goal.name} is {goal.horizon_years} years — long-term, three phases. "
                f"Present only current phase one now: {phases[0]['duration_years']} years, "
                f"eighty percent equity, fifteen percent debt, five percent gold. Explain that "
                f"this goal-based portfolio uses the user's risk profile and top category funds "
                f"for the right risk-return mix; mention future phases only as glide-down context.")
    elif bucket == "medium":
        hint = (f"{goal.name} is {goal.horizon_years} years — medium-term, two phases. "
                f"Present only current phase one now: {phases[0]['duration_years']} years, "
                f"fifty percent equity, forty percent debt, ten percent gold. Explain that the "
                f"portfolio uses top category funds chosen for the user's risk profile and "
                f"the right risk-return mix; mention "
                f"the later debt-heavy phase only as glide-down context.")
    else:
        hint = (f"{goal.name} is {goal.horizon_years} years — short-term, one phase. "
                f"Present the current phase: ninety-five percent debt and five percent gold, "
                f"using top category funds for the user's risk profile, with focus on downside "
                f"protection, liquidity and the right risk-return mix.")

    return tool_response(STATE.proposed_portfolios[goal.name], hint)


async def generate_plan_pdf(args: dict) -> dict:
    if not STATE.goals or not STATE.ratios:
        return missing("a complete plan",
                       "Finish goals, ratios and the portfolio before generating the PDF.")
    path = plan_pdf.generate_pdf(STATE)
    STATE.plan_pdf_path = path
    filename = path.split("/")[-1]
    url = f"/output/{filename}"
    logger.opt(colors=True).info(f"<green>📄 PLAN PDF READY: {path}</green>")
    logger.opt(colors=True).info(f"<green>📄 Serving at: {url}</green>")
    return tool_response(
        {"pdf_file": filename, "url": url},
        "The plan PDF is ready — tell them it's done, give three action items, and close warmly.")


# ---------------------------------------------------------------- schemas

_NUM = {"type": "number"}

TOOL_SPECS = [
    (assess_risk_profile, "Score the user's verbatim answers to the 2 behavioral risk scenario questions into a risk profile.",
     {"answers": {"type": "array", "items": {"type": "string"},
                  "description": "The user's verbatim answers to the 2 scenario questions, in order"}}, ["answers"]),
    (add_family, "Capture family details: spouse age, children with ages, other dependents count.",
     {"spouse_age": {"type": "integer", "description": "Age of spouse if any, omit otherwise"},
      "children": {"type": "array", "items": {"type": "object", "properties": {"age": {"type": "integer"}}},
                   "description": "List of children with their ages"},
      "dependents_count": {"type": "integer", "description": "Other dependents (e.g., parents); 0 if none"}},
     []),
    (pull_mf_central, "Fetch the caller's existing mutual fund portfolio from MF Central (mocked). Call only after Maya has explained MF Central, why the data is needed, and the user explicitly agrees to trigger OTP. The browser will request mock OTP 1234.",
     {"user_confirmed_consent": {"type": "boolean", "description": "True only after the user explicitly agrees to trigger the MF Central OTP"},
      "consent_context": {"type": "string", "description": "Brief summary of what Maya explained before triggering OTP"},
      "holding_edits": {"type": "array",
                        "description": "Optional corrections to MF Central holdings",
                        "items": {"type": "object",
                                  "properties": {"fund": {"type": "string"},
                                                 "current_value": {"type": "number"},
                                                 "monthly_sip": {"type": "number"}}}}},
     ["user_confirmed_consent", "consent_context"]),
    (pull_account_aggregator, "Pull bank, EPF, NPS, stocks and cash flows via Finvu Account Aggregator (mocked). Call first only after Maya has explained AA, what data is pulled, why it helps, and the user explicitly agrees to trigger OTP. Later correction calls reuse consent.",
     {"user_confirmed_consent": {"type": "boolean", "description": "True only after the user explicitly agrees to trigger the Finvu OTP"},
      "consent_context": {"type": "string", "description": "Brief summary of what Maya explained before triggering OTP"},
      "monthly_income": {"type": "number", "description": "Optional user-corrected monthly income"},
      "monthly_expenses": {"type": "number", "description": "Optional user-corrected monthly non-EMI expenses"},
      "monthly_emi": {"type": "number", "description": "Optional user-corrected monthly EMI"},
      "investments": {"type": "number", "description": "Optional user-corrected monthly investments from bank statement"},
      "household_expenses": {"type": "number", "description": "Optional user-corrected household expenses"},
      "utilities": {"type": "number", "description": "Optional user-corrected utilities"},
      "entertainment": {"type": "number", "description": "Optional user-corrected entertainment"},
      "epf": {"type": "number", "description": "Optional user-corrected EPF value"},
      "nps": {"type": "number", "description": "Optional user-corrected NPS value"},
      "stocks": {"type": "number", "description": "Optional user-corrected stocks value"}},
     ["user_confirmed_consent", "consent_context"]),
    (add_manual_asset, "Add a voice-mentioned asset that AA didn't return — PPF, FD, gold, real estate, US stocks, international stocks, etc.",
     {"name": {"type": "string", "description": "User-friendly label like 'PPF account'"},
      "asset_type": {"type": "string", "description": "Category: ppf, fd, gold, real_estate, us_stocks, international_stocks, other"},
      "value": {"type": "number", "description": "Current value in INR"}},
     ["name", "value"]),
    (confirm_financial_snapshot, "Mark the financial snapshot ready for goals. Call only after the user explicitly confirms the AA-derived income, expenses, EMIs, EPF, NPS and stocks are correct, and has answered whether to add extra investments such as PPF, FDs, gold, real estate, US stocks or international stocks.",
     {"user_confirmed_financial_data": {"type": "boolean", "description": "True only after the user explicitly says the AA data looks correct or is good to go"},
      "user_answered_additional_assets": {"type": "boolean", "description": "True only after the user answered the additional-investments question"},
      "confirmation_context": {"type": "string", "description": "Brief summary of the user's confirmation and additions/no additions"}},
     ["user_confirmed_financial_data", "user_answered_additional_assets", "confirmation_context"]),
    (add_goal, "Register a financial goal (max 4) and get its inflation-adjusted future cost. For an emergency fund, omit target_amount_today so the tool uses six months of confirmed monthly outflow.",
     {"name": {"type": "string"}, "target_amount_today": {"type": "number", "description": "Cost in today's rupees"},
      "horizon_years": {"type": "integer"}, "priority": {"type": "integer", "description": "1 = most important"}},
     ["name", "priority"]),
    (project_existing_corpus, "Project the existing portfolio to a goal's horizon and earmark it (waterfall by priority).",
     {"goal_name": {"type": "string"}}, ["goal_name"]),
    (compute_gap_and_sip, "Compute the funding gap and required monthly SIP for a goal, with affordability.",
     {"goal_name": {"type": "string"},
      "expected_return": {"type": "number", "description": "Override annual return as decimal; omit to use risk profile default"}},
     ["goal_name"]),
    (reprioritize, "Re-fund goals in priority order within the user's comfortable monthly budget; returns trade-offs.",
     {"max_affordable_sip": {"type": "number", "description": "Monthly amount the user is comfortable investing"}},
     ["max_affordable_sip"]),
    (build_goal_portfolio, "Build the phased portfolio for a single goal: horizon decides phase count (short=1, medium=2, long=3) and allocation. Call once per funded goal.",
     {"goal_name": {"type": "string"}}, ["goal_name"]),
    (generate_plan_pdf, "Generate the final financial plan PDF from everything gathered.", {}, []),
]


def register_tools(llm) -> ToolsSchema:
    """Register all 9 handlers on the LLM service; returns the ToolsSchema for the context."""
    schemas = []
    for fn, description, properties, required in TOOL_SPECS:
        schemas.append(FunctionSchema(name=fn.__name__, description=description,
                                      properties=properties, required=required))
        llm.register_function(fn.__name__, _wrap(fn))
    return ToolsSchema(standard_tools=schemas)


def _wrap(fn):
    """Console-log every tool call (the demo debug view) and never let one crash the call."""
    async def handler(params: FunctionCallParams):
        logger.opt(colors=True).info(
            f"<yellow>🔧 TOOL CALL {fn.__name__}({json.dumps(dict(params.arguments))})</yellow>")
        try:
            result = await fn(dict(params.arguments))
        except Exception as e:
            logger.exception(f"Tool {fn.__name__} failed")
            result = {"error": str(e),
                      "instruction": "Apologize briefly and try a different step."}
        logger.opt(colors=True).info(
            f"<cyan>🔧 TOOL RESULT {fn.__name__} → {json.dumps(result, default=str)[:600]}</cyan>")
        await params.result_callback(result)
        # Push the updated state to the browser UI (no-op for voice-only / tests).
        await ui_bus.emit({"type": "state", "payload": snapshot(last_event=fn.__name__)})
    return handler
