// Mirror of core/session.py snapshot() — the live state the bot pushes over RTVI.

export interface Holding {
  fund: string;
  type: string;
  current_value: number;
  monthly_sip: number;
  rating: number;
  flag: string | null;
}

export interface Portfolio {
  holdings: Holding[];
  total_value: number;
  total_monthly_sip: number;
  equity_value: number;
  debt_value: number;
  underperformers: string[];
}

export interface Ratios {
  surplus: number;
  savings_rate: number;
  savings_band: string;
  debt_to_income: number;
  dti_band: string;
  idle_surplus: number;
}

export interface Goal {
  name: string;
  target_amount_today: number;
  horizon_years: number;
  priority: number;
  inflated_target: number | null;
  projected_from_existing: number | null;
  required_sip: number | null;
  funded: boolean;
}

export interface Family {
  spouse_age: number | null;
  children: { age: number }[];
  dependents_count: number;
}

export interface AaAssets {
  epf: number;
  nps: number;
  stocks: number;
}

export interface ExpenseBreakdown {
  investments: number;
  emis: number;
  household_expenses: number;
  utilities: number;
  entertainment: number;
}

export interface ManualAsset {
  name: string;
  asset_type: string;
  value: number;
}

export interface Fund {
  fund: string;
  bucket: string;
  monthly_sip: number;
  rationale: string;
}

export interface Phase {
  phase: number;
  duration_years: number;
  allocation: { equity: number; debt: number; gold: number };
  funds: Fund[];
}

export interface ProposedPortfolio {
  goal: string;
  horizon_bucket: string;
  horizon_years: number;
  monthly_sip: number;
  phases: Phase[];
  current_phase: Phase;
  selection_basis: string;
}

export type Progress = Record<string, "done" | "pending">;

export interface Snapshot {
  name: string | null;
  age: number | null;
  monthly_income: number | null;
  monthly_expenses: number | null;
  monthly_emi: number | null;
  expense_breakdown: ExpenseBreakdown | null;
  ratios: Ratios | null;
  risk_profile: string | null;
  family: Family | null;
  aa_assets: AaAssets | null;
  financial_snapshot_confirmed: boolean;
  additional_assets: ManualAsset[];
  portfolio: Portfolio | null;
  goals: Goal[];
  proposed_portfolios: Record<string, ProposedPortfolio>;
  plan_pdf_url: string | null;
  progress: Progress;
  last_event: string | null;
}
