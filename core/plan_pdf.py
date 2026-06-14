"""Render the financial plan in SessionState to a 2-page PDF with reportlab."""

import os
import time

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .session import SessionState

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")


def _inr(x: float | None) -> str:
    if x is None:
        return "—"
    x = float(x)
    if x >= 1e7:
        return f"Rs {x / 1e7:.2f} Cr"
    if x >= 1e5:
        return f"Rs {x / 1e5:.1f} L"
    return f"Rs {x:,.0f}"


def generate_pdf(state: SessionState) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    safe_name = (state.name or "client").strip().lower().replace(" ", "_")
    path = os.path.join(OUTPUT_DIR, f"plan_{safe_name}_{time.strftime('%Y%m%d_%H%M%S')}.pdf")

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=20, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=colors.HexColor("#1a4d8f"))
    body = styles["BodyText"]
    table_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a4d8f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f6fb")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ])

    story = [
        Paragraph("Your Financial Plan", h1),
        Paragraph(f"Prepared for <b>{state.name or 'Client'}</b> · {time.strftime('%d %b %Y')} · Wealth Expert", body),
        Spacer(1, 6 * mm),
    ]

    # Page 1: snapshot
    story.append(Paragraph("Financial Snapshot", h2))
    r = state.ratios or {}
    snapshot = [
        ["Monthly income", _inr(state.monthly_income)],
        ["Monthly non-EMI expenses", _inr(state.monthly_expenses)],
        ["Monthly EMI", _inr(state.monthly_emi or 0)],
        ["Monthly surplus", _inr(r.get("surplus"))],
        ["Savings rate", f"{r.get('savings_rate', 0) * 100:.0f}% ({r.get('savings_band', '—')})"],
        ["Debt-to-income", f"{r.get('debt_to_income', 0) * 100:.0f}% ({r.get('dti_band', '—')})"],
        ["Risk profile", (state.risk_profile or "—").title()],
    ]
    story.append(Table(snapshot, colWidths=[60 * mm, 80 * mm],
                       style=TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                                         ("FONTSIZE", (0, 0), (-1, -1), 9),
                                         ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                                         ("LEFTPADDING", (0, 0), (-1, -1), 6)])))
    story.append(Spacer(1, 6 * mm))

    if state.expense_breakdown:
        story.append(Paragraph("Expense Breakdown (3-Month Average)", h2))
        rows = [["Category", "Monthly average"]]
        for key, value in state.expense_breakdown.items():
            rows.append([key.replace("_", " ").title(), _inr(value)])
        story.append(Table(rows, colWidths=[70 * mm, 50 * mm], style=table_style))
        story.append(Spacer(1, 6 * mm))

    if state.portfolio:
        p = state.portfolio
        story.append(Paragraph("Existing Portfolio", h2))
        rows = [["Fund", "Type", "Value", "Monthly SIP", "Rating"]]
        for h in p["holdings"]:
            name = h["fund"] + (" (!)" if h.get("flag") else "")
            rows.append([name, h["type"], _inr(h["current_value"]), _inr(h["monthly_sip"]), f"{h['rating']}/5"])
        rows.append(["Total", "", _inr(p["total_value"]), _inr(p["total_monthly_sip"]), ""])
        story.append(Table(rows, colWidths=[62 * mm, 20 * mm, 30 * mm, 30 * mm, 18 * mm], style=table_style))
        if p.get("review_methodology"):
            story.append(Paragraph(p["review_methodology"], body))
        if p["underperformers"]:
            story.append(Paragraph(
                f"(!) Flagged underperformers to switch out: {', '.join(p['underperformers'])}.", body))
            for review in p.get("fund_reviews", []):
                if review.get("status") != "good":
                    story.append(Paragraph(f"{review['fund']}: {review['reason']}.", body))
        story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("Your Goals", h2))
    rows = [["Goal", "Today's cost", "Future cost", "Covered by existing", "Monthly SIP", "Status"]]
    for g in sorted(state.goals, key=lambda g: g.priority):
        coverage = "—"
        if g.projected_from_existing is not None and g.inflated_target:
            coverage = f"{_inr(g.projected_from_existing)} ({g.projected_from_existing / g.inflated_target * 100:.0f}%)"
        rows.append([
            f"{g.priority}. {g.name} ({g.horizon_years}y)",
            _inr(g.target_amount_today),
            _inr(g.inflated_target),
            coverage,
            _inr(g.required_sip),
            "Funded" if g.funded else "Parked",
        ])
    story.append(Table(rows, colWidths=[42 * mm, 24 * mm, 24 * mm, 34 * mm, 24 * mm, 16 * mm], style=table_style))
    story.append(PageBreak())

    # Page 2: recommendation + actions
    story.append(Paragraph("Recommended Portfolio (Phased by Goal)", h2))
    if state.proposed_portfolios:
        total_sip = sum(pp["monthly_sip"] for pp in state.proposed_portfolios.values())
        story.append(Paragraph(
            f"Total monthly investment across all goals: <b>{_inr(total_sip)}</b>. "
            f"Each goal is phased by its horizon — short-term goals run one debt-heavy phase, "
            f"medium-term goals run two phases (balanced → debt), long-term goals run three "
            f"phases (equity-heavy → balanced → debt glide-down).", body))
        story.append(Spacer(1, 4 * mm))
        for pp in state.proposed_portfolios.values():
            story.append(Paragraph(
                f"<b>{pp['goal']}</b> — {pp['horizon_bucket']}-term, {pp['horizon_years']} years · "
                f"Monthly SIP {_inr(pp['monthly_sip'])}", body))
            story.append(Paragraph(pp.get("selection_basis", ""), body))
            current = pp.get("current_phase") or pp["phases"][0]
            a = current["allocation"]
            alloc = f"{a['equity'] * 100:.0f}/{a['debt'] * 100:.0f}/{a['gold'] * 100:.0f}"
            rows = [["Current phase", "Years", "Allocation", "Fund", "Monthly SIP"]]
            for i, f in enumerate(current["funds"]):
                rows.append([
                    f"P{current['phase']}" if i == 0 else "",
                    f"{current['duration_years']}y" if i == 0 else "",
                    alloc if i == 0 else "",
                    f["fund"],
                    _inr(f["monthly_sip"]),
                ])
            story.append(Table(rows, colWidths=[14 * mm, 14 * mm, 26 * mm, 60 * mm, 26 * mm],
                               style=table_style))
            if len(pp["phases"]) > 1:
                future = ", ".join(f"P{ph['phase']} for {ph['duration_years']}y" for ph in pp["phases"][1:])
                story.append(Paragraph(f"Future glide path: {future}.", body))
            story.append(Spacer(1, 4 * mm))
    else:
        story.append(Paragraph("To be finalized with your advisor.", body))
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("Action Plan", h2))
    actions = []
    if state.portfolio and state.portfolio["underperformers"]:
        actions.append(f"Switch out of underperformers: {', '.join(state.portfolio['underperformers'])}.")
    if state.proposed_portfolios:
        total_sip = sum(pp["monthly_sip"] for pp in state.proposed_portfolios.values())
        actions.append(f"Start the new monthly SIP of {_inr(total_sip)} across the per-goal "
                       f"current-phase portfolios above. Each goal glides between phases as it approaches.")
    parked = [g.name for g in state.goals if not g.funded]
    if parked:
        actions.append(f"Revisit parked goal(s) — {', '.join(parked)} — when income grows.")
    actions.append("Review this plan every 12 months or after any major life event.")
    for i, a in enumerate(actions, 1):
        story.append(Paragraph(f"{i}. {a}", body))

    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph(
        "<font size=7 color='#888888'>Generated by Wealth Expert (demo). Assumed returns: equity 11%, debt 7%. "
        "Mutual fund investments are subject to market risks. This is not investment advice.</font>", body))

    SimpleDocTemplate(path, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm).build(story)
    return path
