"""Run deterministic eval tests and render a small standalone HTML report."""

from __future__ import annotations

import html
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "evaluation_report.html"

TEST_TARGETS = [
    "tests/test_gold_plan_eval.py",
    "tests/test_tool_call_sequence.py",
    "tests/test_tool_guards.py",
    "tests/test_portfolio_plan_contract.py",
]

TEST_CASES = {
    "tests/test_gold_plan_eval.py::test_gold_manual_asset_end_to_end_plan_eval": {
        "area": "End-to-end gold plan",
        "case": "Complete deterministic gold plan",
        "expectation": (
            "Risk, family, MF Central, Finvu, manual gold, goals, SIP gap, "
            "gold portfolio allocation, and PDF generation all complete."
        ),
    },
    "tests/test_tool_call_sequence.py::test_registered_tool_names_match_planning_contract": {
        "area": "Tool-call contract",
        "case": "Registered tool names",
        "expectation": "The LLM-facing registry exposes the expected planning tool set in flow order.",
    },
    "tests/test_tool_call_sequence.py::test_gold_plan_uses_expected_tool_call_sequence": {
        "area": "Tool-call contract",
        "case": "Gold-plan tool sequence",
        "expectation": (
            "The deterministic gold-plan scenario calls risk, family, consent pulls, "
            "manual gold, financial confirmation, goals, gap, portfolio, and PDF tools in order."
        ),
    },
    "tests/test_tool_guards.py::test_mf_central_requires_explicit_consent": {
        "area": "Consent guard",
        "case": "MF Central consent required",
        "expectation": "MF Central pull is rejected until user consent is explicit.",
    },
    "tests/test_tool_guards.py::test_account_aggregator_requires_mf_central_first": {
        "area": "Consent guard",
        "case": "Finvu waits for MF Central",
        "expectation": "Finvu Account Aggregator is blocked until MF Central succeeds.",
    },
    "tests/test_tool_guards.py::test_account_aggregator_correction_reuses_existing_consent": {
        "area": "Consent guard",
        "case": "AA correction reuses consent",
        "expectation": "Correcting AA data after the first pull does not request another OTP.",
    },
    "tests/test_tool_guards.py::test_financial_snapshot_confirmation_requires_manual_assets_answer": {
        "area": "Financial snapshot gate",
        "case": "Manual-asset answer required",
        "expectation": "Goals remain blocked until the user answers the PPF/FD/gold/etc. question.",
    },
    "tests/test_portfolio_plan_contract.py::test_short_term_portfolio_has_debt_heavy_gold_hedge": {
        "area": "Portfolio contract",
        "case": "Short-term gold hedge",
        "expectation": "Short-term goals use one debt-heavy phase with five percent gold.",
    },
    "tests/test_portfolio_plan_contract.py::test_medium_term_portfolio_glides_to_more_debt_and_keeps_gold": {
        "area": "Portfolio contract",
        "case": "Medium-term glide path",
        "expectation": "Medium-term goals use two phases and keep gold exposure.",
    },
    "tests/test_portfolio_plan_contract.py::test_long_term_portfolio_has_three_phase_equity_glide_down_with_gold": {
        "area": "Portfolio contract",
        "case": "Long-term glide path",
        "expectation": "Long-term goals use three phases, reduce equity, and keep gold exposure.",
    },
    "tests/test_portfolio_plan_contract.py::test_every_phase_allocation_sums_to_one": {
        "area": "Portfolio contract",
        "case": "Allocation totals",
        "expectation": "Every phase allocation sums to one hundred percent.",
    },
}


def _node_id(case: ET.Element) -> str:
    path = case.attrib.get("file")
    name = case.attrib.get("name", "")
    if path:
        return f"{path}::{name}"
    classname = case.attrib.get("classname", "").replace(".", "/")
    return f"{classname}.py::{name}"


def _status(case: ET.Element) -> tuple[str, str]:
    failure = case.find("failure")
    error = case.find("error")
    skipped = case.find("skipped")
    if failure is not None:
        return "failed", failure.attrib.get("message") or (failure.text or "")
    if error is not None:
        return "error", error.attrib.get("message") or (error.text or "")
    if skipped is not None:
        return "skipped", skipped.attrib.get("message") or (skipped.text or "")
    return "passed", ""


def _run_pytest(junit_path: Path) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        *TEST_TARGETS,
        "-q",
        f"--junitxml={junit_path}",
    ]
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)


def _parse_cases(junit_path: Path) -> list[dict]:
    root = ET.parse(junit_path).getroot()
    rows = []
    for case in root.iter("testcase"):
        node_id = _node_id(case)
        meta = TEST_CASES.get(node_id, {})
        status, detail = _status(case)
        rows.append({
            "node_id": node_id,
            "area": meta.get("area", "Unmapped"),
            "case": meta.get("case", case.attrib.get("name", "")),
            "expectation": meta.get("expectation", "No description registered."),
            "status": status,
            "time": float(case.attrib.get("time", "0") or 0),
            "detail": detail,
        })
    return rows


def _render(rows: list[dict], result: subprocess.CompletedProcess[str]) -> str:
    passed = sum(1 for row in rows if row["status"] == "passed")
    failed = sum(1 for row in rows if row["status"] in {"failed", "error"})
    skipped = sum(1 for row in rows if row["status"] == "skipped")
    generated_at = datetime.now().strftime("%d %b %Y, %I:%M %p")

    row_html = []
    for row in rows:
        detail = ""
        if row["detail"]:
            detail = f"<pre>{html.escape(row['detail'])}</pre>"
        row_html.append(f"""
        <tr>
          <td><span class="pill {row['status']}">{html.escape(row['status'].upper())}</span></td>
          <td>{html.escape(row['area'])}</td>
          <td>
            <strong>{html.escape(row['case'])}</strong>
            <div class="expectation">{html.escape(row['expectation'])}</div>
            <code>{html.escape(row['node_id'])}</code>
            {detail}
          </td>
          <td>{row['time']:.2f}s</td>
        </tr>
        """)

    stdout = html.escape(result.stdout.strip())
    stderr = html.escape(result.stderr.strip())
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Wealth Expert Deterministic Evaluation Report</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #15202b;
      --muted: #64748b;
      --line: #d8dee8;
      --pass: #0f7a3b;
      --fail: #b42318;
      --skip: #8a5a00;
      --accent: #174ea6;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header {{
      background: #0f172a;
      color: white;
      padding: 36px 44px;
    }}
    header p {{
      color: #cbd5e1;
      max-width: 880px;
      line-height: 1.5;
      margin: 10px 0 0;
    }}
    main {{ padding: 28px 44px 44px; }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(4, minmax(140px, 1fr));
      gap: 14px;
      margin-bottom: 22px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
    }}
    .metric {{
      display: block;
      font-size: 30px;
      font-weight: 750;
      line-height: 1;
    }}
    .label {{
      color: var(--muted);
      font-size: 13px;
      margin-top: 8px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 14px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      background: #eef2f7;
      color: #334155;
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }}
    tr:last-child td {{ border-bottom: 0; }}
    code {{
      display: inline-block;
      margin-top: 8px;
      color: #475569;
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    pre {{
      white-space: pre-wrap;
      background: #fff1f0;
      border: 1px solid #ffccc7;
      border-radius: 6px;
      padding: 10px;
      color: #7a1f17;
      max-height: 260px;
      overflow: auto;
    }}
    .expectation {{
      color: var(--muted);
      margin-top: 4px;
      line-height: 1.45;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 76px;
      border-radius: 999px;
      padding: 5px 9px;
      font-size: 12px;
      font-weight: 750;
    }}
    .passed {{ background: #dcfce7; color: var(--pass); }}
    .failed, .error {{ background: #fee2e2; color: var(--fail); }}
    .skipped {{ background: #fef3c7; color: var(--skip); }}
    details {{
      margin-top: 22px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    details pre {{
      background: #f8fafc;
      border-color: var(--line);
      color: #334155;
    }}
    @media (max-width: 760px) {{
      header, main {{ padding-left: 18px; padding-right: 18px; }}
      .summary {{ grid-template-columns: 1fr 1fr; }}
      th:nth-child(2), td:nth-child(2), th:nth-child(4), td:nth-child(4) {{ display: none; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Wealth Expert Deterministic Evaluation Report</h1>
    <p>
      Gold-plan evals for Maya's goal-based financial planning flow. These tests
      bypass live LLM, STT, TTS, and WebRTC, then verify deterministic tool
      contracts, consent gates, manual gold capture, portfolio gold allocation,
      and final PDF generation.
    </p>
  </header>
  <main>
    <section class="summary">
      <div class="card"><span class="metric">{len(rows)}</span><div class="label">Total cases</div></div>
      <div class="card"><span class="metric">{passed}</span><div class="label">Passed</div></div>
      <div class="card"><span class="metric">{failed}</span><div class="label">Failed / errored</div></div>
      <div class="card"><span class="metric">{skipped}</span><div class="label">Skipped</div></div>
    </section>
    <div class="card" style="margin-bottom: 22px;">
      <strong>Generated:</strong> {html.escape(generated_at)}
      <span style="color: var(--muted); margin-left: 14px;">Command: <code>python scripts/generate_eval_report.py</code></span>
    </div>
    <table>
      <thead>
        <tr>
          <th>Status</th>
          <th>Area</th>
          <th>Test case</th>
          <th>Runtime</th>
        </tr>
      </thead>
      <tbody>
        {''.join(row_html)}
      </tbody>
    </table>
    <details>
      <summary>Raw pytest output</summary>
      <pre>{stdout}</pre>
      {f'<pre>{stderr}</pre>' if stderr else ''}
    </details>
  </main>
</body>
</html>
"""


def main() -> int:
    os.makedirs(OUTPUT.parent, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        junit_path = Path(tmp) / "eval-junit.xml"
        result = _run_pytest(junit_path)
        rows = _parse_cases(junit_path) if junit_path.exists() else []
        OUTPUT.write_text(_render(rows, result), encoding="utf-8")
        print(f"Evaluation report written to {OUTPUT}")
        if rows:
            print(f"{sum(1 for row in rows if row['status'] == 'passed')}/{len(rows)} cases passed")
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
