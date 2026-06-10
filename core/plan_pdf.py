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
        ["Monthly expenses", _inr(state.monthly_expenses)],
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

    if state.portfolio:
        p = state.portfolio
        story.append(Paragraph("Existing Portfolio", h2))
        rows = [["Fund", "Type", "Value", "Monthly SIP", "Rating"]]
        for h in p["holdings"]:
            name = h["fund"] + (" (!)" if h.get("flag") else "")
            rows.append([name, h["type"], _inr(h["current_value"]), _inr(h["monthly_sip"]), f"{h['rating']}/5"])
        rows.append(["Total", "", _inr(p["total_value"]), _inr(p["total_monthly_sip"]), ""])
        story.append(Table(rows, colWidths=[62 * mm, 20 * mm, 30 * mm, 30 * mm, 18 * mm], style=table_style))
        if p["underperformers"]:
            story.append(Paragraph(
                f"(!) Flagged underperformers to switch out: {', '.join(p['underperformers'])}.", body))
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
    story.append(Paragraph("Recommended Portfolio", h2))
    if state.proposed_portfolio:
        pp = state.proposed_portfolio
        story.append(Paragraph(
            f"Total monthly investment: <b>{_inr(pp['monthly_sip'])}</b> · "
            f"Allocation: {pp['allocation']['equity'] * 100:.0f}% equity / "
            f"{pp['allocation']['debt'] * 100:.0f}% debt / {pp['allocation']['gold'] * 100:.0f}% gold", body))
        rows = [["Fund", "Bucket", "Monthly SIP", "Why"]]
        for f in pp["funds"]:
            rows.append([f["fund"], f["bucket"], _inr(f["monthly_sip"]), Paragraph(f["rationale"], body)])
        story.append(Table(rows, colWidths=[45 * mm, 18 * mm, 25 * mm, 72 * mm], style=table_style))
    else:
        story.append(Paragraph("To be finalized with your advisor.", body))
    story.append(Spacer(1, 8 * mm))

    story.append(Paragraph("Action Plan", h2))
    actions = []
    if state.portfolio and state.portfolio["underperformers"]:
        actions.append(f"Switch out of underperformers: {', '.join(state.portfolio['underperformers'])}.")
    if state.proposed_portfolio:
        actions.append(f"Start the new monthly SIP of {_inr(state.proposed_portfolio['monthly_sip'])} "
                       f"across the recommended funds above.")
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
