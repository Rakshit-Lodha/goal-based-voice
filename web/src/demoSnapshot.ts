import type { Snapshot } from "./types";

// Baked sample state for previewing the UI without a live call: open with ?demo=1.
export const DEMO_SNAPSHOT: Snapshot = {
  name: "Rakshit",
  age: 28,
  monthly_income: 150000,
  monthly_expenses: 70000,
  monthly_emi: 25000,
  expense_breakdown: {
    investments: 20000,
    emis: 25000,
    household_expenses: 30000,
    utilities: 8000,
    entertainment: 12000,
  },
  ratios: {
    surplus: 55000,
    savings_rate: 0.3667,
    savings_band: "average",
    debt_to_income: 0.1667,
    dti_band: "average",
    idle_surplus: 43000,
  },
  risk_profile: "aggressive",
  family: {
    spouse_age: 27,
    children: [{ age: 3 }],
    dependents_count: 0,
  },
  aa_assets: {
    epf: 450000,
    nps: 50000,
    stocks: 500000,
  },
  financial_snapshot_confirmed: true,
  additional_assets: [
    { name: "PPF account", asset_type: "ppf", value: 200000 },
  ],
  portfolio: {
    holdings: [
      { fund: "Bluechip Large Cap Fund", type: "equity", current_value: 520000, monthly_sip: 5000, rating: 4, flag: null },
      { fund: "Flexi Cap Opportunities Fund", type: "equity", current_value: 410000, monthly_sip: 4000, rating: 4, flag: null },
      { fund: "Midcap Momentum Fund", type: "equity", current_value: 280000, monthly_sip: 0, rating: 2, flag: "underperformer" },
      { fund: "Thematic Infra Fund", type: "equity", current_value: 150000, monthly_sip: 0, rating: 1, flag: "underperformer" },
      { fund: "Short Duration Debt Fund", type: "debt", current_value: 290000, monthly_sip: 3000, rating: 4, flag: null },
      { fund: "Liquid Fund", type: "debt", current_value: 150000, monthly_sip: 0, rating: 3, flag: null },
    ],
    total_value: 1800000,
    total_monthly_sip: 12000,
    equity_value: 1360000,
    debt_value: 440000,
    underperformers: ["Midcap Momentum Fund", "Thematic Infra Fund"],
  },
  goals: [
    { name: "Emergency fund", target_amount_today: 570000, horizon_years: 1, priority: 1, inflated_target: 570000, projected_from_existing: 570000, required_sip: 0, funded: true },
    { name: "Buy a house in Pune", target_amount_today: 10000000, horizon_years: 10, priority: 2, inflated_target: 19671514, projected_from_existing: 7160004, required_sip: 50500, funded: true },
    { name: "Daughter's education", target_amount_today: 3000000, horizon_years: 12, priority: 3, inflated_target: 9415285, projected_from_existing: 0, required_sip: 9500, funded: true },
  ],
  proposed_portfolios: {
    "Buy a house in Pune": {
      goal: "Buy a house in Pune",
      horizon_bucket: "long",
      horizon_years: 10,
      monthly_sip: 50500,
      selection_basis: "Funds selected for the user's risk profile and goal horizon using return profile, downside protection, volatility and role in the phase.",
      phases: [
        {
          phase: 1,
          duration_years: 5,
          allocation: { equity: 0.8, debt: 0.15, gold: 0.05 },
          funds: [
            { fund: "Nifty 50 Index Fund", bucket: "equity", monthly_sip: 24000, rationale: "Low-cost core owning India's 50 biggest companies." },
            { fund: "Flexi Cap Fund", bucket: "equity", monthly_sip: 16000, rationale: "Manager moves across caps for extra growth." },
            { fund: "Short Duration Debt Fund", bucket: "debt", monthly_sip: 5500, rationale: "Steady low-volatility cushion." },
            { fund: "Gold ETF Fund of Fund", bucket: "gold", monthly_sip: 2500, rationale: "Hedge that holds up when equity wobbles." },
          ],
        },
        { phase: 2, duration_years: 3, allocation: { equity: 0.5, debt: 0.4, gold: 0.1 }, funds: [] },
        { phase: 3, duration_years: 2, allocation: { equity: 0.2, debt: 0.7, gold: 0.1 }, funds: [] },
      ],
      current_phase: {
        phase: 1,
        duration_years: 5,
        allocation: { equity: 0.8, debt: 0.15, gold: 0.05 },
        funds: [
          { fund: "Nifty 50 Index Fund", bucket: "equity", monthly_sip: 24000, rationale: "Low-cost core owning India's 50 biggest companies." },
          { fund: "Flexi Cap Fund", bucket: "equity", monthly_sip: 16000, rationale: "Manager moves across caps for extra growth." },
          { fund: "Short Duration Debt Fund", bucket: "debt", monthly_sip: 5500, rationale: "Steady low-volatility cushion." },
          { fund: "Gold ETF Fund of Fund", bucket: "gold", monthly_sip: 2500, rationale: "Hedge that holds up when equity wobbles." },
        ],
      },
    },
  },
  plan_pdf_url: null,
  progress: { risk: "done", family: "done", mfc: "done", aa: "done", finances: "done", goals: "done", gap: "done", portfolio_plan: "done", pdf: "pending" },
  last_event: "build_goal_portfolio",
};
