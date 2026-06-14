import { useCallback, useState } from "react";
import type { FormEvent } from "react";
import type { TransportState } from "@pipecat-ai/client-js";
import { usePipecatClient } from "@pipecat-ai/client-react";
import { useRtviEvent } from "./pcReact";
import { API_BASE, OFFER_URL } from "./pcClient";
import { DEMO_SNAPSHOT } from "./demoSnapshot";
import type { Snapshot } from "./types";
import { inr, pct, titleCase } from "./format";

const DEMO = new URLSearchParams(window.location.search).has("demo");

const STAGES: [string, string][] = [
  ["risk", "Risk"],
  ["family", "Family"],
  ["mfc", "MF Central"],
  ["aa", "Finvu AA"],
  ["goals", "Goals"],
  ["gap", "Gap & SIP"],
  ["portfolio_plan", "Plan"],
  ["pdf", "Document"],
];

// Which card should flash when a given tool last fired.
const EVENT_CARD: Record<string, string> = {
  pull_mf_central: "portfolio",
  pull_account_aggregator: "snapshot",
  add_family: "family",
  add_manual_asset: "assets",
  add_goal: "goals",
  project_existing_corpus: "goals",
  compute_gap_and_sip: "goals",
  reprioritize: "goals",
  assess_risk_profile: "risk",
  build_goal_portfolio: "allocation",
  generate_plan_pdf: "plan",
};

export default function Dashboard() {
  const client = usePipecatClient();
  const [snap, setSnap] = useState<Snapshot | null>(DEMO ? DEMO_SNAPSHOT : null);
  const [otp, setOtp] = useState<{ request_id: string; provider: string } | null>(null);
  const [otpValue, setOtpValue] = useState("");
  const [otpError, setOtpError] = useState<string | null>(null);
  const [state, setState] = useState<TransportState>("disconnected");
  const [dialing, setDialing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pulseCard, setPulseCard] = useState<string | null>(null);

  useRtviEvent("transportStateChanged", (s) => {
    const st = s as TransportState;
    setState(st);
    if (st === "disconnected" || st === "error") setDialing(false);
  });
  useRtviEvent("serverMessage", (data) => {
    const msg = data as { type?: string; payload?: Snapshot | { request_id: string; provider: string } };
    if (msg?.type === "state" && msg.payload) {
      const nextSnap = msg.payload as Snapshot;
      setSnap(nextSnap);
      const card = nextSnap.last_event ? EVENT_CARD[nextSnap.last_event] : null;
      if (card) {
        setPulseCard(card);
        window.setTimeout(() => setPulseCard(null), 1400);
      }
    } else if (msg?.type === "otp_request" && msg.payload) {
      setOtp(msg.payload as { request_id: string; provider: string });
      setOtpValue("");
      setOtpError(null);
    }
  });

  const live = state === "connected" || state === "ready";
  const connecting = dialing && !live; // only while a call we initiated is establishing

  const connect = useCallback(async () => {
    setError(null);
    setDialing(true);
    try {
      await client?.connect({ webrtcRequestParams: { endpoint: OFFER_URL } });
    } catch (e) {
      console.error("connect failed", e);
      setError(`Couldn't reach Maya. Is the backend running? (.venv/bin/python server.py on :8000)${errorSuffix(e)}`);
      setDialing(false);
    }
  }, [client]);

  const disconnect = useCallback(async () => {
    setDialing(false);
    await client?.disconnect();
    setSnap(null);
    setOtp(null);
  }, [client]);

  const cardClass = (id: string) => `card${pulseCard === id ? " pulse" : ""}`;

  const submitOtp = useCallback(async (e: FormEvent) => {
    e.preventDefault();
    if (!otp) return;
    setOtpError(null);
    try {
      const res = await fetch(`${API_BASE}/api/otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_id: otp.request_id, otp: otpValue }),
      });
      const body = await res.json();
      if (!body.accepted) {
        setOtpError("This OTP request is no longer active. Wait for Maya to trigger it again.");
        return;
      }
      setOtp(null);
      setOtpValue("");
    } catch (e) {
      setOtpError(`Couldn't submit OTP: ${String(e)}`);
    }
  }, [otp, otpValue]);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="dot" />
          <div>
            <h1>Wealth Expert</h1>
            <p>Live goal-based planning with Maya</p>
          </div>
        </div>
        <div className="conn">
          <span className={`status status-${live ? "live" : connecting ? "wait" : "off"}`}>
            {live ? "● Live — Maya is listening" : connecting ? "Connecting…" : "Not connected"}
          </span>
          {live ? (
            <button className="btn btn-ghost" onClick={disconnect}>
              End call
            </button>
          ) : (
            <button className="btn btn-primary" onClick={connect} disabled={connecting}>
              {connecting ? "Connecting…" : "Start call"}
            </button>
          )}
        </div>
      </header>

      {error && <div className="banner-error">{error}</div>}

      {otp && (
        <form className="otp-strip" onSubmit={submitOtp}>
          <label>
            <span>{otp.provider} OTP</span>
            <input
              autoFocus
              inputMode="numeric"
              pattern="[0-9 ]*"
              placeholder="Enter OTP"
              value={otpValue}
              onChange={(e) => setOtpValue(e.target.value)}
            />
          </label>
          <button className="btn btn-primary" type="submit" disabled={!otpValue.trim()}>
            Submit
          </button>
          {otpError && <p>{otpError}</p>}
        </form>
      )}

      <div className="layout">
        {/* Left rail: stage progress */}
        <aside className="rail">
          <h3>Session progress</h3>
          <ol>
            {STAGES.map(([key, label]) => {
              const done = snap?.progress?.[key] === "done";
              return (
                <li key={key} className={done ? "done" : ""}>
                  <span className="tick">{done ? "✓" : ""}</span>
                  {label}
                </li>
              );
            })}
          </ol>
          {snap?.name && <div className="client-chip">Client: <b>{snap.name}</b>{snap.age ? `, ${snap.age}` : ""}</div>}
        </aside>

        {/* Right: live cards */}
        <main className="grid">
          {!snap && (
            <div className="empty">
              <div className="empty-inner">
                <h2>Press “Start call” and say hello</h2>
                <p>
                  Maya will greet the KYC-verified client, ask risk and family context, then
                  use simple mock OTP input for MF Central and Finvu. Watch this space fill in
                  as you talk — every number here comes
                  straight from a tool, never the model.
                </p>
              </div>
            </div>
          )}

          {snap?.ratios && (
            <section className={cardClass("snapshot")}>
              <h2>Finvu Financial Snapshot</h2>
              <div className="kpis">
                <Kpi label="Monthly income" value={inr(snap.monthly_income)} sub="3-month average" />
                <Kpi label="Monthly surplus" value={inr(snap.ratios.surplus)} />
                <Kpi label="Savings rate" value={pct(snap.ratios.savings_rate)} sub={snap.ratios.savings_band} tone={band(snap.ratios.savings_band)} />
                <Kpi label="Idle surplus" value={inr(snap.ratios.idle_surplus)} sub="not invested" tone="warn" />
              </div>
              {snap.expense_breakdown && (
                <table className="mt">
                  <thead><tr><th>Expense category</th><th className="r">Monthly average</th></tr></thead>
                  <tbody>
                    {Object.entries(snap.expense_breakdown).map(([key, value]) => (
                      <tr key={key}>
                        <td>{titleCase(key.replace("_", " "))}</td>
                        <td className="r">{inr(value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          )}

          {snap?.family && (
            <section className={cardClass("family")}>
              <h2>Family Context</h2>
              <div className="kpis">
                <Kpi label="Spouse age" value={snap.family.spouse_age != null ? String(snap.family.spouse_age) : "—"} />
                <Kpi label="Children" value={String(snap.family.children.length)} sub={snap.family.children.map((c) => `${c.age}y`).join(", ") || "none"} />
                <Kpi label="Other dependents" value={String(snap.family.dependents_count)} />
              </div>
            </section>
          )}

          {snap?.aa_assets && (
            <section className={cardClass("assets")}>
              <h2>Other Investments <span className="muted">· Account Aggregator</span></h2>
              <div className="kpis">
                <Kpi label="EPF" value={inr(snap.aa_assets.epf)} />
                <Kpi label="NPS" value={inr(snap.aa_assets.nps)} />
                <Kpi label="Stocks" value={inr(snap.aa_assets.stocks)} />
                <Kpi label="Manual extras" value={inr(snap.additional_assets.reduce((sum, a) => sum + a.value, 0))} sub={`${snap.additional_assets.length} item(s)`} />
              </div>
              {snap.additional_assets.length > 0 && (
                <table className="mt">
                  <thead><tr><th>Name</th><th>Type</th><th className="r">Value</th></tr></thead>
                  <tbody>
                    {snap.additional_assets.map((a) => (
                      <tr key={`${a.name}-${a.asset_type}`}>
                        <td>{a.name}</td><td>{titleCase(a.asset_type.replace("_", " "))}</td><td className="r">{inr(a.value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          )}

          {snap?.portfolio && (
            <section className={cardClass("portfolio")}>
              <h2>
                Existing Portfolio
                <span className="muted"> · {inr(snap.portfolio.total_value)} · {inr(snap.portfolio.total_monthly_sip)}/mo SIP</span>
              </h2>
              <table>
                <thead>
                  <tr><th>Fund</th><th>Type</th><th className="r">Value</th><th className="r">SIP</th><th className="r">Rating</th></tr>
                </thead>
                <tbody>
                  {snap.portfolio.holdings.map((h) => (
                    <tr key={h.fund} className={h.flag ? "flag" : ""}>
                      <td>{h.fund}{h.flag && <span className="badge">underperformer</span>}</td>
                      <td>{h.type}</td>
                      <td className="r">{inr(h.current_value)}</td>
                      <td className="r">{inr(h.monthly_sip)}</td>
                      <td className="r">{h.rating}/5</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          {snap?.risk_profile && (
            <section className={cardClass("risk")}>
              <h2>Risk Profile</h2>
              <RiskGauge profile={snap.risk_profile} />
            </section>
          )}

          {snap && snap.goals.length > 0 && (
            <section className={cardClass("goals")}>
              <h2>Goals</h2>
              <table>
                <thead>
                  <tr>
                    <th>Goal</th><th className="r">Today</th><th className="r">Future</th>
                    <th>Covered by existing</th><th className="r">Monthly SIP</th><th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {[...snap.goals].sort((a, b) => a.priority - b.priority).map((g) => {
                    const cov = g.projected_from_existing != null && g.inflated_target
                      ? g.projected_from_existing / g.inflated_target : null;
                    return (
                      <tr key={g.name} className={g.funded ? "" : "parked"}>
                        <td>{g.priority}. {g.name} <span className="muted">({g.horizon_years}y)</span></td>
                        <td className="r">{inr(g.target_amount_today)}</td>
                        <td className="r">{inr(g.inflated_target)}</td>
                        <td>
                          {cov != null ? (
                            <div className="cov">
                              <div className="cov-bar"><span style={{ width: `${Math.min(100, cov * 100)}%` }} /></div>
                              <span className="cov-pct">{pct(cov)}</span>
                            </div>
                          ) : "—"}
                        </td>
                        <td className="r">{inr(g.required_sip)}</td>
                        <td>{g.funded ? <span className="pill pill-ok">Funded</span> : <span className="pill pill-park">Parked</span>}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </section>
          )}

          {snap && Object.keys(snap.proposed_portfolios).length > 0 && (
            <section className={cardClass("allocation")}>
              <h2>Goal Portfolios</h2>
              {Object.values(snap.proposed_portfolios).map((pp) => (
                <div className="goal-plan" key={pp.goal}>
                  <h3>{pp.goal} <span className="muted">· {titleCase(pp.horizon_bucket)} · {inr(pp.monthly_sip)}/mo</span></h3>
                  <p className="muted phase-note">{pp.selection_basis}</p>
                  <div className="phase">
                    <Donut alloc={pp.current_phase.allocation} />
                    <div className="phase-body">
                      <div className="fund-head"><b>Current phase {pp.current_phase.phase}</b><span>{pp.current_phase.duration_years} years</span></div>
                      <ul className="funds">
                        {pp.current_phase.funds.map((f) => (
                          <li key={`${pp.goal}-${pp.current_phase.phase}-${f.fund}`}>
                            <div className="fund-head"><b>{f.fund}</b><span className="r">{inr(f.monthly_sip)}</span></div>
                            <p className="muted">{f.rationale}</p>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                  {pp.phases.length > 1 && (
                    <p className="muted phase-note">
                      Future glide path: {pp.phases.map((phase) => `phase ${phase.phase} for ${phase.duration_years}y`).join(", ")}.
                    </p>
                  )}
                </div>
              ))}
            </section>
          )}

          {snap?.plan_pdf_url && (
            <section className={`${cardClass("plan")} plan-cta`}>
              <h2>Your Plan is Ready</h2>
              <a className="btn btn-primary" href={`${API_BASE}${snap.plan_pdf_url}`} target="_blank" rel="noreferrer">
                Open plan PDF
              </a>
            </section>
          )}
        </main>
      </div>
    </div>
  );
}

function Kpi({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="kpi">
      <span className="kpi-label">{label}</span>
      <span className="kpi-value">{value}</span>
      {sub && <span className={`kpi-sub tone-${tone ?? "neutral"}`}>{sub}</span>}
    </div>
  );
}

function band(b: string): string {
  if (["good", "strong", "healthy"].includes(b)) return "ok";
  if (["bad", "low", "stretched"].includes(b)) return "warn";
  return "neutral";
}

function errorSuffix(e: unknown): string {
  if (e instanceof Error && e.message) return ` — ${e.message}`;
  if (typeof e === "string" && e) return ` — ${e}`;
  return "";
}

function RiskGauge({ profile }: { profile: string }) {
  const order = ["conservative", "balanced", "aggressive"];
  const idx = order.indexOf(profile);
  return (
    <div className="risk">
      <div className="risk-track">
        {order.map((p, i) => (
          <div key={p} className={`risk-seg seg-${i}${i === idx ? " active" : ""}`}>{titleCase(p)}</div>
        ))}
      </div>
      <p className="muted">
        {profile === "conservative" && "Capital safety first — ~30% equity, 9% expected return."}
        {profile === "balanced" && "Steady growth with cushioning — ~55% equity, 11% expected return."}
        {profile === "aggressive" && "Growth-focused, rides volatility — ~75% equity, 13% expected return."}
      </p>
    </div>
  );
}

function Donut({ alloc }: { alloc: { equity: number; debt: number; gold: number } }) {
  const eq = alloc.equity * 100;
  const debt = eq + alloc.debt * 100;
  const style = {
    background: `conic-gradient(var(--accent) 0 ${eq}%, var(--blue2) ${eq}% ${debt}%, var(--gold) ${debt}% 100%)`,
  };
  return (
    <div className="donut-wrap">
      <div className="donut" style={style}><div className="donut-hole" /></div>
      <ul className="legend">
        <li><span className="sw" style={{ background: "var(--accent)" }} />Equity {pct(alloc.equity)}</li>
        <li><span className="sw" style={{ background: "var(--blue2)" }} />Debt {pct(alloc.debt)}</li>
        <li><span className="sw" style={{ background: "var(--gold)" }} />Gold {pct(alloc.gold)}</li>
      </ul>
    </div>
  );
}
