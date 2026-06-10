"""The 9 tools: schemas + handlers. Tools own ALL math; the LLM only converses.

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
from core import plan_pdf, portfolio_data
from core.session import STATE, Goal, get_goal, missing, tool_response


# ---------------------------------------------------------------- handlers

async def get_existing_portfolio(args: dict) -> dict:
    name = args["name"]
    STATE.name = name
    STATE.portfolio = portfolio_data.lookup(name)
    p = STATE.portfolio
    under = p["underperformers"]
    hint = (f"Portfolio of {fm.round_to_500(p['total_value']) / 1e5:.0f} lakhs across "
            f"{len(p['holdings'])} funds with {p['total_monthly_sip']} rupees of monthly SIPs. ")
    if under:
        hint += f"{len(under)} of {len(p['holdings'])} funds are underperformers dragging returns: {', '.join(under)}."
    else:
        hint += "No red flags — a clean portfolio."
    return tool_response(p, hint)


async def compute_financial_ratios(args: dict) -> dict:
    STATE.monthly_income = float(args["monthly_income"])
    STATE.monthly_expenses = float(args["monthly_expenses"])
    STATE.monthly_emi = float(args.get("monthly_emi") or 0)
    existing_sip = STATE.portfolio["total_monthly_sip"] if STATE.portfolio else 0
    STATE.ratios = fm.financial_ratios(
        STATE.monthly_income, STATE.monthly_expenses, STATE.monthly_emi, existing_sip)
    r = STATE.ratios
    hint = (f"Savings rate is {r['savings_band']} ({r['savings_rate'] * 100:.0f} percent), "
            f"debt load is {r['dti_band']}. Of the {r['surplus']} rupees monthly surplus, "
            f"{r['idle_surplus']} rupees is idle — not invested anywhere.")
    return tool_response(r, hint)


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
    if len(STATE.goals) >= 3:
        return missing("room for another goal",
                       "Three goals are already captured — that's the maximum. Move on.")
    horizon = int(args["horizon_years"])
    if horizon < 1:
        return missing("a valid horizon", "Ask for a target year at least 1 year away.")
    name = args["name"]
    amount = float(args["target_amount_today"])
    inflation = fm.inflation_for_goal(name)
    goal = Goal(
        name=name,
        target_amount_today=amount,
        horizon_years=horizon,
        priority=int(args["priority"]),
        inflated_target=round(fm.inflate(amount, horizon, inflation)),
    )
    STATE.goals.append(goal)
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
                       "Call get_existing_portfolio with the caller's name first.")
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
        return missing("income and expenses",
                       "Collect income, expenses, EMIs and call compute_financial_ratios first.")
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


async def build_portfolio(args: dict) -> dict:
    if not STATE.risk_profile:
        return missing("the risk profile", "Call assess_risk_profile first.")
    monthly_sip = float(args["monthly_sip"])
    eq, debt, gold = fm.ALLOCATION[STATE.risk_profile]
    funds = [
        {"fund": "Nifty 50 Index Fund", "bucket": "equity",
         "monthly_sip": fm.round_to_500(monthly_sip * eq * 0.60),
         "rationale": "Low-cost core that simply owns India's 50 biggest companies."},
        {"fund": "Flexi Cap Fund", "bucket": "equity",
         "monthly_sip": fm.round_to_500(monthly_sip * eq * 0.40),
         "rationale": "Lets the manager move across large, mid and small caps for extra growth."},
        {"fund": "Short Duration Debt Fund", "bucket": "debt",
         "monthly_sip": fm.round_to_500(monthly_sip * debt),
         "rationale": "Steady, low-volatility cushion for the nearer-term goals."},
    ]
    if gold > 0:
        funds.append({"fund": "Gold ETF Fund of Fund", "bucket": "gold",
                      "monthly_sip": fm.round_to_500(monthly_sip * gold),
                      "rationale": "A small hedge that holds up when equity wobbles."})
    funds = [f for f in funds if f["monthly_sip"] > 0]
    STATE.proposed_portfolio = {
        "monthly_sip": round(monthly_sip),
        "risk_profile": STATE.risk_profile,
        "allocation": {"equity": eq, "debt": debt, "gold": gold},
        "funds": funds,
    }
    hint = (f"A {STATE.risk_profile} mix: {eq * 100:.0f} percent equity, {debt * 100:.0f} percent "
            f"debt, {gold * 100:.0f} percent gold, spread across {len(funds)} simple funds.")
    return tool_response(STATE.proposed_portfolio, hint)


async def generate_plan_pdf(args: dict) -> dict:
    if not STATE.goals or not STATE.ratios:
        return missing("a complete plan",
                       "Finish goals, ratios and the portfolio before generating the PDF.")
    path = plan_pdf.generate_pdf(STATE)
    STATE.plan_pdf_path = path
    filename = path.split("/")[-1]
    url = f"http://localhost:7861/{filename}"
    logger.opt(colors=True).info(f"<green>📄 PLAN PDF READY: {path}</green>")
    logger.opt(colors=True).info(f"<green>📄 Serving at: {url}</green>")
    return tool_response(
        {"pdf_file": filename, "url": url},
        "The plan PDF is ready — tell them it's done, give three action items, and close warmly.")


# ---------------------------------------------------------------- schemas

_NUM = {"type": "number"}

TOOL_SPECS = [
    (get_existing_portfolio, "Fetch the caller's existing mutual fund portfolio from MF Central by name.",
     {"name": {"type": "string", "description": "Caller's first name"}}, ["name"]),
    (compute_financial_ratios, "Compute surplus, savings rate, debt-to-income and idle surplus from monthly cash flows (INR).",
     {"monthly_income": _NUM, "monthly_expenses": _NUM,
      "monthly_emi": {"type": "number", "description": "Total monthly EMIs, 0 if none"}},
     ["monthly_income", "monthly_expenses"]),
    (assess_risk_profile, "Score the user's verbatim answers to the behavioral risk scenario questions into a risk profile.",
     {"answers": {"type": "array", "items": {"type": "string"},
                  "description": "The user's verbatim answers to 2-3 scenario questions"}}, ["answers"]),
    (add_goal, "Register a financial goal (max 3) and get its inflation-adjusted future cost.",
     {"name": {"type": "string"}, "target_amount_today": {"type": "number", "description": "Cost in today's rupees"},
      "horizon_years": {"type": "integer"}, "priority": {"type": "integer", "description": "1 = most important"}},
     ["name", "target_amount_today", "horizon_years", "priority"]),
    (project_existing_corpus, "Project the existing portfolio to a goal's horizon and earmark it (waterfall by priority).",
     {"goal_name": {"type": "string"}}, ["goal_name"]),
    (compute_gap_and_sip, "Compute the funding gap and required monthly SIP for a goal, with affordability.",
     {"goal_name": {"type": "string"},
      "expected_return": {"type": "number", "description": "Override annual return as decimal; omit to use risk profile default"}},
     ["goal_name"]),
    (reprioritize, "Re-fund goals in priority order within the user's comfortable monthly budget; returns trade-offs.",
     {"max_affordable_sip": {"type": "number", "description": "Monthly amount the user is comfortable investing"}},
     ["max_affordable_sip"]),
    (build_portfolio, "Build the recommended fund-level portfolio for the agreed total monthly SIP.",
     {"monthly_sip": {"type": "number"}}, ["monthly_sip"]),
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
    return handler
