"use client";

import { useState, useEffect } from "react";
import Nav from "@/components/shell/Nav";
import { useCustomer } from "@/lib/customer-context";
import ErrorState from "@/components/shell/ErrorState";
import TopBar from "@/components/shell/TopBar";
import AitoPanel from "@/components/shell/AitoPanel";
import { apiFetch } from "@/lib/api";
import type { AitoPanelConfig } from "@/lib/types";

const PANEL: AitoPanelConfig = {
  operation: "_search (aggregates)",
  stats: [
    { value: "78%", label: "Automation" },
    { value: "63%", label: "Aito share" },
    { value: "$invoices", label: "Records" },
    { value: "Indexed", label: "Model" },
  ],
  description: "Quality overview aggregates from the invoices and overrides tables. Automation breakdown computed from routed_by field.",
  query: JSON.stringify({ from: "invoices", where: {}, limit: 300 }, null, 2),
  links: [{ label: "Quality monitoring docs", url: "https://aito.ai/docs" }],
};

interface QualityData {
  automation: { total: number; rule: number; aito: number; human: number; rule_pct: number; aito_pct: number; human_pct: number; automation_rate: number };
  overrides: { total: number; by_field: Record<string, number> };
  override_patterns: { corrected_to: string; field: string; count: number; lift: number }[];
}

function BarRow({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const pct = max > 0 ? (value / max) * 100 : 0;
  return (
    <div className="bar-row">
      <div className="bar-label">{label}</div>
      <div className="bar-track"><div className={`bar-fill ${color}`} style={{ width: `${pct}%` }} /></div>
      <div className="bar-val">{value}%</div>
    </div>
  );
}

interface AuditRow {
  log_id: string;
  field: string;
  predicted_value: string | null;
  user_value: string | null;
  source: string;
  confidence: number;
  accepted: boolean;
  timestamp: number;
}

interface AuditData {
  rows: AuditRow[];
  by_field: Record<string, { total: number; accepted: number; overridden: number; accept_rate: number }>;
  totals: { total: number; accepted: number; overridden: number; accept_rate: number };
}

export default function QualityOverviewPage() {
  const { customerId } = useCustomer();
  const [data, setData] = useState<QualityData | null>(null);
  const [audit, setAudit] = useState<AuditData | null>(null);
  const [live, setLive] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    setData(null); setAudit(null); setLive(false); setError(false);
    apiFetch<QualityData>(`/api/quality/overview?customer_id=${customerId}`)
      .then((d) => { setData(d); setLive(true); })
      .catch(() => setError(true));
    apiFetch<AuditData>(`/api/quality/audit?customer_id=${encodeURIComponent(customerId)}&limit=12`)
      .then((d) => setAudit(d))
      .catch(() => {});
  }, [customerId]);

  const a = data?.automation;

  return (
    <>
      <Nav />
      <div className="main">
        <TopBar breadcrumb="Quality" title="System Overview" subtitle="Automation breakdown from live data" live={live} />
        <div className="content">
          <div className="metrics">
            <div className="metric highlight"><div className="metric-label">Overall automation</div><div className="metric-value">{a ? `${a.automation_rate}%` : "--"}</div><div className="metric-sub metric-up">{a ? `\u2191 from ${a.rule_pct}% rules-only` : ""}</div></div>
            <div className="metric"><div className="metric-label">Rules coverage</div><div className="metric-value">{a?.rule_pct ?? "--"}%</div><div className="metric-sub metric-neutral">{a?.rule ?? "--"} rule-routed</div></div>
            <div className="metric"><div className="metric-label">Aito coverage</div><div className="metric-value">{a?.aito_pct ?? "--"}%</div></div>
            <div className="metric"><div className="metric-label">Human review</div><div className="metric-value">{a?.human_pct ?? "--"}%</div></div>
          </div>
          <div className="quality-grid">
            <div className="quality-card">
              <div className="qc-header"><span className="qc-title">Processing source breakdown</span></div>
              <div className="qc-body">
                {a && (
                  <div style={{ display: "flex", height: 24, borderRadius: 4, overflow: "hidden", gap: 1, marginBottom: 16 }}>
                    <div style={{ width: `${a.rule_pct}%`, background: "var(--blue)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, color: "#fff", fontWeight: 500 }}>Rules {a.rule_pct}%</div>
                    <div style={{ width: `${a.aito_pct}%`, background: "var(--gold-mid)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, color: "#0d1520", fontWeight: 500 }}>Aito {a.aito_pct}%</div>
                    <div style={{ width: `${a.human_pct}%`, background: "var(--border2)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, color: "var(--text3)", fontWeight: 500 }}>{a.human_pct}%</div>
                  </div>
                )}
                <div style={{ fontSize: "11.5px", color: "var(--text3)", lineHeight: 1.6 }}>
                  Rules are precise but cover only {a?.rule_pct ?? "..."}% of cases. Aito extends coverage to {a?.automation_rate ?? "..."}% total.
                </div>
              </div>
            </div>
            <div className="quality-card">
              <div className="qc-header"><span className="qc-title">Override summary</span></div>
              <div className="qc-body">
                {data && (data.overrides?.total ?? 0) < 3 ? (
                  <div style={{ fontSize: 12, color: "var(--text3)", lineHeight: 1.6 }}>
                    Few overrides for this customer yet. Patterns emerge as the
                    customer accumulates more invoice history. Try a larger
                    customer (e.g. CUST-0000) to see Aito learn from human
                    corrections at scale.
                  </div>
                ) : (
                  <>
                    <div style={{ fontSize: 24, fontWeight: 600, fontFamily: "'IBM Plex Mono', monospace", marginBottom: 12 }}>{data?.overrides?.total ?? "--"}</div>
                    <div style={{ fontSize: 11, color: "var(--text3)", marginBottom: 12 }}>total overrides</div>
                    {data?.overrides?.by_field && Object.entries(data.overrides.by_field).sort(([,a],[,b]) => b - a).map(([field, count]) => (
                      <div key={field} className="bar-row">
                        <div className="bar-label">{field}</div>
                        <div className="bar-track"><div className="bar-fill bar-fill-gold" style={{ width: `${(count / data.overrides.total) * 100}%` }} /></div>
                        <div className="bar-val">{count}</div>
                      </div>
                    ))}
                  </>
                )}
              </div>
            </div>
          </div>

          {audit && audit.totals.total > 0 && (
            <div className="quality-card" style={{ marginTop: 16 }}>
              <div className="qc-header" style={{ display: "flex", justifyContent: "space-between" }}>
                <span className="qc-title">Audit log · prediction_log table</span>
                <span className="card-hint">SOX evidence: predicted vs accepted, per submission</span>
              </div>
              <div className="qc-body">
                <div style={{ display: "flex", gap: 18, marginBottom: 14, fontSize: 12 }}>
                  <span><strong>{audit.totals.total}</strong> total submissions</span>
                  <span style={{ color: "var(--green)" }}><strong>{audit.totals.accepted}</strong> accepted ({Math.round(audit.totals.accept_rate * 100)}%)</span>
                  <span style={{ color: "var(--gold-dark)" }}><strong>{audit.totals.overridden}</strong> overridden</span>
                </div>

                {Object.keys(audit.by_field).length > 0 && (
                  <div style={{ marginBottom: 14 }}>
                    <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", marginBottom: 6 }}>Accept rate by field</div>
                    {Object.entries(audit.by_field).sort(([,a],[,b]) => b.total - a.total).map(([field, b]) => (
                      <BarRow key={field} label={field} value={Math.round(b.accept_rate * 100)} max={100} color="bar-fill-blue" />
                    ))}
                  </div>
                )}

                <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", marginBottom: 6 }}>
                  Most recent decisions
                </div>
                <div style={{ overflowX: "auto" }}>
                  <table className="table" style={{ fontSize: 11, width: "100%" }}>
                    <thead>
                      <tr>
                        <th style={{ textAlign: "left", padding: "4px 8px", borderBottom: "1px solid var(--border2)" }}>When</th>
                        <th style={{ textAlign: "left", padding: "4px 8px", borderBottom: "1px solid var(--border2)" }}>Field</th>
                        <th style={{ textAlign: "left", padding: "4px 8px", borderBottom: "1px solid var(--border2)" }}>Predicted</th>
                        <th style={{ textAlign: "left", padding: "4px 8px", borderBottom: "1px solid var(--border2)" }}>User value</th>
                        <th style={{ textAlign: "right", padding: "4px 8px", borderBottom: "1px solid var(--border2)" }}>Conf.</th>
                        <th style={{ textAlign: "center", padding: "4px 8px", borderBottom: "1px solid var(--border2)" }}>Outcome</th>
                      </tr>
                    </thead>
                    <tbody>
                      {audit.rows.map((r) => (
                        <tr key={r.log_id} style={{ borderBottom: "1px solid var(--border2)" }}>
                          <td className="mono" style={{ padding: "4px 8px", color: "var(--text3)", fontSize: 10 }}>
                            {new Date(r.timestamp * 1000).toISOString().slice(0, 16).replace("T", " ")}
                          </td>
                          <td style={{ padding: "4px 8px", fontFamily: "'IBM Plex Mono', monospace" }}>{r.field}</td>
                          <td style={{ padding: "4px 8px", color: "var(--text2)" }}>{r.predicted_value ?? "—"}</td>
                          <td style={{ padding: "4px 8px", color: "var(--text)", fontWeight: r.accepted ? 400 : 600 }}>
                            {r.user_value ?? "—"}
                          </td>
                          <td className="mono" style={{ padding: "4px 8px", textAlign: "right", color: "var(--text3)" }}>
                            {(r.confidence * 100).toFixed(0)}%
                          </td>
                          <td style={{ padding: "4px 8px", textAlign: "center" }}>
                            {r.accepted
                              ? <span className="badge badge-green">Accepted</span>
                              : <span className="badge badge-amber">Overridden</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
      <AitoPanel config={PANEL} />
    </>
  );
}
