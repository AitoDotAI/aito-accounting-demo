"use client";

import { useState, useEffect, Fragment } from "react";
import Nav from "@/components/shell/Nav";
import { useCustomer } from "@/lib/customer-context";
import TopBar from "@/components/shell/TopBar";
import AitoPanel from "@/components/shell/AitoPanel";
import GovernanceStepper from "@/components/governance/GovernanceStepper";
import ConfidenceBar from "@/components/prediction/ConfidenceBar";
import ErrorState from "@/components/shell/ErrorState";
import { apiFetch } from "@/lib/api";
import type { AitoPanelConfig } from "@/lib/types";

const PANEL: AitoPanelConfig = {
  operation: "_predict (replay)",
  stats: [{ value: "--", label: "Rules" }, { value: "--", label: "Avg precision" }, { value: "Indexed", label: "Model" }, { value: "$invoices", label: "Records" }],
  description: "Rule precision measured by replaying each rule against this customer's invoices and comparing the predicted GL code to the actual one.",
  query: JSON.stringify({ from: "invoices", where: { vendor: "Telia Finland" }, predict: "gl_code" }, null, 2),
  links: [{ label: "Rule evaluation docs", url: "https://aito.ai/docs" }],
};

interface RulePerf {
  rule: string;
  fires_on: string;
  coverage: string;
  precision: number;
  total_matches: number;
  correct: number;
  disagreeing?: number;
  owner?: string;
  last_reviewed?: string;
  trend: string;
  status: string;
}

interface RulesData {
  rules: RulePerf[];
}

interface DriftRule {
  rule_name: string;
  vendor: string;
  gl_code: string;
  current_precision: number;
  first_precision: number;
  delta: number;
  series: number[];
}

interface DriftData {
  rules: DriftRule[];
  weekly_overrides: { weeks_ago: number; count: number }[];
}

function Sparkline({ values, width = 80, height = 22 }: { values: number[]; width?: number; height?: number }) {
  if (!values.length) return null;
  const min = Math.min(...values, 0.5);
  const max = Math.max(...values, 1.0);
  const range = max - min || 0.001;
  const points = values
    .map((v, i) => {
      const x = (i / Math.max(1, values.length - 1)) * (width - 4) + 2;
      const y = height - 2 - ((v - min) / range) * (height - 4);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const trend = values[values.length - 1] - values[0];
  const stroke = trend < -0.05 ? "var(--red)" : trend > 0.02 ? "var(--green)" : "var(--gold-mid)";
  return (
    <svg width={width} height={height} style={{ display: "block" }}>
      <polyline points={points} fill="none" stroke={stroke} strokeWidth={1.5} />
    </svg>
  );
}

export default function RulePerformancePage() {
  const { customerId, currentCustomer } = useCustomer();
  const [data, setData] = useState<RulesData | null>(null);
  const [drift, setDrift] = useState<DriftData | null>(null);
  const [live, setLive] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    setData(null); setDrift(null); setLive(false); setError(null);
    apiFetch<RulesData>(`/api/quality/rules?customer_id=${customerId}`)
      .then((d) => { setData(d); setLive(true); })
      .catch((e) => setError(e));
    apiFetch<DriftData>(`/api/quality/rules/drift?customer_id=${customerId}`)
      .then((d) => setDrift(d))
      .catch(() => {});
  }, [customerId]);

  const backfillDrift = async () => {
    await fetch(`/api/quality/rules/backfill?customer_id=${customerId}`, { method: "POST" });
    apiFetch<DriftData>(`/api/quality/rules/drift?customer_id=${customerId}`)
      .then((d) => setDrift(d));
  };

  const rules = data?.rules ?? [];
  const avgPrecision = rules.length > 0
    ? rules.reduce((sum, r) => sum + r.precision, 0) / rules.length
    : 0;

  return (
    <>
      <Nav />
      <div className="main">
        <TopBar
          breadcrumb="Governance · 3. Measure"
          title="Rule Performance"
          subtitle={
            data
              ? `${rules.length} rules · ${currentCustomer?.invoice_count?.toLocaleString() ?? ""} invoices replayed`
              : error
                ? "Backend not reachable"
                : "Loading..."
          }
          live={live}
        />
        <GovernanceStepper active="measure" />
        <div className="content">
          {error && <ErrorState error={error} />}
          {drift && drift.rules.length === 0 && (
            <div style={{ background: "var(--surface2)", border: "1px solid var(--border2)", borderRadius: 6, padding: "12px 16px", marginBottom: 12, fontSize: 12, color: "var(--text2)", lineHeight: 1.5 }}>
              No rule history yet for this customer.{" "}
              <button onClick={backfillDrift} style={{ background: "var(--gold-dark)", color: "#f5e8c0", border: "none", padding: "3px 12px", borderRadius: 3, cursor: "pointer", fontSize: 11, fontWeight: 600, fontFamily: "inherit" }}>
                Backfill 12 weeks
              </button>{" "}
              to populate the drift charts. Real production builds this via a weekly snapshot cron.
            </div>
          )}
          {drift && drift.rules.length > 0 && (
            <div className="card" style={{ marginBottom: 12 }}>
              <div className="card-header">
                <span className="card-title">12-week drift</span>
                <span className="card-hint">Per-rule precision over time · sorted by largest drop</span>
              </div>
              <div style={{ padding: "12px 16px", display: "grid", gridTemplateColumns: "1fr auto auto auto auto", gap: "8px 16px", alignItems: "center" }}>
                <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", fontWeight: 600 }}>Rule</div>
                <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", fontWeight: 600 }}>12wk ago</div>
                <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", fontWeight: 600 }}>Now</div>
                <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", fontWeight: 600 }}>Δ</div>
                <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", fontWeight: 600 }}>Trend</div>
                {drift.rules.slice(0, 8).map((r) => {
                  const deltaColor = r.delta < -0.05 ? "var(--red)" : r.delta > 0.02 ? "var(--green)" : "var(--text2)";
                  return (
                    <Fragment key={r.rule_name}>
                      <div style={{ fontSize: 12, color: "var(--text2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        <span style={{ fontFamily: "'IBM Plex Mono', monospace", color: "var(--gold-dark)", marginRight: 4 }}>{r.gl_code}</span>
                        {r.vendor}
                      </div>
                      <div className="mono" style={{ fontSize: 11, color: "var(--text3)" }}>{(r.first_precision * 100).toFixed(0)}%</div>
                      <div className="mono" style={{ fontSize: 11 }}>{(r.current_precision * 100).toFixed(0)}%</div>
                      <div className="mono" style={{ fontSize: 11, color: deltaColor, fontWeight: 600 }}>
                        {r.delta >= 0 ? "+" : ""}{(r.delta * 100).toFixed(1)}pp
                      </div>
                      <Sparkline values={r.series} />
                    </Fragment>
                  );
                })}
              </div>
            </div>
          )}
          {drift && drift.weekly_overrides.length > 0 && (
            <div className="card" style={{ marginBottom: 12 }}>
              <div className="card-header">
                <span className="card-title">Weekly overrides</span>
                <span className="card-hint">Rising override count = rules need review</span>
              </div>
              <div style={{ padding: "16px", display: "flex", alignItems: "flex-end", gap: 4, height: 80 }}>
                {(() => {
                  const max = Math.max(1, ...drift.weekly_overrides.map((w) => w.count));
                  return drift.weekly_overrides.map((w) => {
                    const h = (w.count / max) * 60;
                    return (
                      <div key={w.weeks_ago} title={`${w.weeks_ago === 0 ? "this week" : `${w.weeks_ago}w ago`}: ${w.count} overrides`} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                        <div style={{ width: "100%", height: `${h}px`, background: w.weeks_ago === 0 ? "var(--gold-dark)" : "var(--gold-mid)", borderRadius: "3px 3px 0 0", minHeight: 2 }} />
                        <div style={{ fontSize: 9, color: "var(--text3)", fontFamily: "'IBM Plex Mono', monospace" }}>
                          {w.weeks_ago === 0 ? "now" : `-${w.weeks_ago}w`}
                        </div>
                      </div>
                    );
                  });
                })()}
              </div>
            </div>
          )}
          {data && (
            <div className="card">
              <div className="card-header">
                <span className="card-title">All rules — precision measured against ground truth</span>
                <span className="card-hint">Avg precision: {(avgPrecision * 100).toFixed(0)}%</span>
              </div>
              <table className="table">
                <thead>
                  <tr>
                    <th>Rule</th>
                    <th>Fires on</th>
                    <th>Owner</th>
                    <th>Last reviewed</th>
                    <th>Matches</th>
                    <th>Disagree</th>
                    <th>Precision</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {rules.map((r, i) => (
                    <tr key={i}>
                      <td className="mono" style={{ fontSize: 11 }}>{r.rule}</td>
                      <td style={{ fontSize: 12 }}>{r.fires_on}</td>
                      <td style={{ fontSize: 12, color: "var(--text2)" }}>{r.owner ?? "Unassigned"}</td>
                      <td className="mono" style={{ fontSize: 11, color: "var(--text3)" }}>{r.last_reviewed ?? "\u2014"}</td>
                      <td className="mono">{r.total_matches.toLocaleString()} <span style={{ fontSize: 10, color: "var(--text3)" }}>({r.coverage})</span></td>
                      <td className="mono" style={{ color: (r.disagreeing ?? 0) > 0 ? "var(--red)" : "var(--text3)" }}>
                        {r.disagreeing ?? 0}
                      </td>
                      <td><ConfidenceBar value={r.precision} /></td>
                      <td>
                        <span className={`badge ${r.status === "Active" ? "badge-green" : r.status === "Drifting" ? "badge-amber" : "badge-red"}`}>{r.status}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
      <AitoPanel config={PANEL} />
    </>
  );
}
