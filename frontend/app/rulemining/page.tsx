"use client";

import { useState, useEffect } from "react";
import Nav from "@/components/shell/Nav";
import { useCustomer } from "@/lib/customer-context";
import ErrorState from "@/components/shell/ErrorState";
import TopBar from "@/components/shell/TopBar";
import AitoPanel from "@/components/shell/AitoPanel";
import LiftHint from "@/components/prediction/LiftHint";
import { apiFetch } from "@/lib/api";
import type { AitoPanelConfig } from "@/lib/types";

const PANEL: AitoPanelConfig = {
  operation: "_relate",
  stats: [
    { value: "30", label: "Patterns" },
    { value: "25", label: "Strong" },
    { value: "$invoices", label: "Records" },
    { value: "Indexed", label: "Model" },
  ],
  description:
    'Rule candidates from <code style="font-size:11px;color:var(--aito-accent)">_relate</code> on the invoice table. ' +
    "Support ratios (33/33) are exact historical counts, not ML estimates.",
  query: JSON.stringify(
    { from: "invoices", where: { category: "telecom" }, relate: "gl_code" },
    null, 2,
  ),
  links: [
    { label: "API reference: _relate", url: "https://aito.ai/docs/api/#post-api-v1-relate" },
  ],
  flow_steps: [
    { n: 1, produces: "Distinct field values", call: "_search invoices LIMIT 100; collect values per condition field" },
    { n: 2, produces: "Each pattern row", call: "_relate WHERE customer_id, field=value → gl_code" },
    { n: 3, produces: "Support, lift, strength", call: "From _relate response: fOnCondition / fCondition, lift" },
    { n: 4, produces: "Drill-down (matching invoices)", call: "_search invoices WHERE customer_id, field=value LIMIT 50" },
  ],
};

interface RuleCandidate {
  pattern: string;
  target: string;
  condition_field: string;
  condition_value: string;
  target_value: string;
  target_label: string;
  support: string;
  support_match: number;
  support_total: number;
  support_ratio: number;
  coverage: number;
  lift: number;
  strength: "strong" | "review" | "weak";
}

interface RulesResponse {
  candidates: RuleCandidate[];
  metrics: { total: number; strong: number; review: number; weak: number; coverage_gain: number };
}

function strengthBadge(s: string) {
  if (s === "strong") return <span className="badge badge-green">Strong</span>;
  if (s === "review") return <span className="badge badge-amber">Review</span>;
  return <span className="badge badge-red">Weak</span>;
}

function supportClass(ratio: number) {
  if (ratio >= 0.95) return "strong";
  if (ratio >= 0.75) return "medium";
  return "weak";
}

interface DrilldownInvoice {
  invoice_id: string;
  vendor: string;
  amount: number;
  gl_code: string;
  category: string;
  invoice_date?: string;
  matched_rule: boolean;
}

export default function RuleMiningPage() {
  const { customerId } = useCustomer();
  const [data, setData] = useState<RulesResponse | null>(null);
  const [live, setLive] = useState(false);
  const [error, setError] = useState(false);
  const [drilldown, setDrilldown] = useState<{ rule: RuleCandidate; invoices: DrilldownInvoice[] } | null>(null);
  const [drillLoading, setDrillLoading] = useState(false);

  useEffect(() => {
    setData(null); setLive(false); setError(false); setDrilldown(null);
    apiFetch<RulesResponse>(`/api/rules/candidates?customer_id=${customerId}`)
      .then((d) => { setData(d); setLive(true); })
      .catch(() => setError(true));
  }, [customerId]);

  const openDrilldown = async (rule: RuleCandidate) => {
    setDrillLoading(true);
    setDrilldown({ rule, invoices: [] });
    try {
      const r = await apiFetch<{ invoices: DrilldownInvoice[] }>(
        `/api/rules/drilldown?customer_id=${customerId}` +
        `&condition_field=${encodeURIComponent(rule.condition_field)}` +
        `&condition_value=${encodeURIComponent(rule.condition_value)}` +
        `&target_value=${encodeURIComponent(rule.target_value)}`
      );
      setDrilldown({ rule, invoices: r.invoices });
    } catch {
      setDrilldown({ rule, invoices: [] });
    } finally {
      setDrillLoading(false);
    }
  };

  const m = data?.metrics;

  return (
    <>
      <Nav />
      <div className="main">
        <TopBar
          breadcrumb="Accounting"
          title="Rule Mining"
          subtitle={m ? `${m.total} patterns discovered via Aito _relate` : error ? "Backend not reachable" : "Loading..."}
          live={live}
        />
        <div className="content">
          <div className="metrics">
            <div className="metric highlight"><div className="metric-label">Candidate rules</div><div className="metric-value">{m?.total ?? "--"}</div></div>
            <div className="metric"><div className="metric-label">Strong (&ge;95%)</div><div className="metric-value">{m?.strong ?? "--"}</div><div className="metric-sub metric-up">Ready to promote</div></div>
            <div className="metric"><div className="metric-label">Coverage gain</div><div className="metric-value">+{m?.coverage_gain ?? "--"}%</div></div>
            <div className="metric"><div className="metric-label">Review</div><div className="metric-value">{m?.review ?? "--"}</div></div>
          </div>
          <div className="card">
            <div className="card-header"><span className="card-title">Candidates ({m?.total ?? "..."})</span><span className="card-hint">From Aito _relate on invoice data</span></div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 80px 80px 80px 100px", padding: "10px 20px", background: "var(--surface2)", borderBottom: "1px solid var(--border2)" }}>
              <div style={{ fontSize: "10.5px", fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px" }}>Pattern</div>
              <div style={{ fontSize: "10.5px", fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", textAlign: "right" }}>Support</div>
              <div style={{ fontSize: "10.5px", fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", textAlign: "right" }}>Coverage</div>
              <div style={{ fontSize: "10.5px", fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", textAlign: "center" }}>Strength</div>
              <div />
            </div>
            {(data?.candidates ?? []).map((c, i) => (
              <div
                key={i}
                className="rule-row"
                onClick={() => openDrilldown(c)}
                style={{ cursor: "pointer" }}
                title="Click to see matching invoices"
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="rule-pattern">
                    When <strong>{c.condition_field}</strong> = <code style={{ fontFamily: "'IBM Plex Mono', monospace", color: "var(--gold-dark)" }}>"{c.condition_value}"</code>
                    {", "} GL is <strong>{c.target_value} ({c.target_label})</strong>
                  </div>
                  <div className="rule-arrow" style={{ marginTop: 4, fontSize: 11, color: "var(--text3)" }}>
                    in {c.support_match} of {c.support_total} cases
                    {c.lift > 1 && <> &middot; <LiftHint value={c.lift} /></>}
                  </div>
                </div>
                <div className={`rule-support ${supportClass(c.support_ratio)}`} style={{ minWidth: 80, textAlign: "right" }}>{Math.round(c.support_ratio * 100)}%</div>
                <div style={{ fontSize: 12, fontFamily: "'IBM Plex Mono', monospace", color: "var(--text2)", minWidth: 80, textAlign: "right" }}>{c.coverage}%</div>
                <div style={{ textAlign: "center" }}>{strengthBadge(c.strength)}</div>
                <div style={{ minWidth: 100, textAlign: "right" }}>
                  {c.strength === "strong" && <span style={{ fontSize: 11, color: "var(--text3)", fontStyle: "italic" }}>drill in &rarr;</span>}
                </div>
              </div>
            ))}
            {!data && !error && Array.from({ length: 6 }).map((_, i) => (
              <div key={`skel-${i}`} style={{ display: "flex", alignItems: "center", padding: 14, borderBottom: "1px solid var(--border2)", gap: 16 }}>
                <div style={{ flex: 1 }}>
                  <div className="skeleton" style={{ height: 14, width: "55%", marginBottom: 6 }} />
                  <div className="skeleton" style={{ height: 11, width: "75%" }} />
                </div>
                <div className="skeleton" style={{ height: 16, width: 80 }} />
                <div className="skeleton" style={{ height: 18, width: 60, borderRadius: 12 }} />
                <div className="skeleton" style={{ height: 24, width: 100, borderRadius: 4 }} />
              </div>
            ))}
            {error && <ErrorState />}
          </div>
        </div>
      </div>
      <AitoPanel config={PANEL} />
      {drilldown && <DrilldownModal drill={drilldown} loading={drillLoading} onClose={() => setDrilldown(null)} />}
    </>
  );
}

function DrilldownModal({
  drill,
  loading,
  onClose,
}: {
  drill: { rule: RuleCandidate; invoices: DrilldownInvoice[] };
  loading: boolean;
  onClose: () => void;
}) {
  const matched = drill.invoices.filter((i) => i.matched_rule);
  const disagreeing = drill.invoices.filter((i) => !i.matched_rule);

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(13, 21, 32, 0.6)", zIndex: 1000,
        display: "flex", alignItems: "center", justifyContent: "center",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--surface)", borderRadius: 8, width: "min(720px, 90vw)",
          maxHeight: "80vh", overflow: "auto", padding: 24,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
          <div>
            <div style={{ fontSize: 11, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", marginBottom: 4 }}>Rule drill-down</div>
            <div style={{ fontSize: 15, fontWeight: 600 }}>
              When <code style={{ fontFamily: "'IBM Plex Mono', monospace", color: "var(--gold-dark)" }}>{drill.rule.condition_field} = "{drill.rule.condition_value}"</code>
            </div>
            <div style={{ fontSize: 13, color: "var(--text2)", marginTop: 4 }}>
              GL is <strong>{drill.rule.target_value} ({drill.rule.target_label})</strong> in {drill.rule.support_match} of {drill.rule.support_total} cases
            </div>
          </div>
          <button onClick={onClose} style={{ background: "transparent", border: "none", fontSize: 20, cursor: "pointer", color: "var(--text3)" }}>×</button>
        </div>

        {loading && <div style={{ padding: 24, textAlign: "center", color: "var(--text3)" }}>Loading matching invoices...</div>}

        {!loading && drill.invoices.length === 0 && (
          <div style={{ padding: 24, textAlign: "center", color: "var(--text3)" }}>No invoices to show.</div>
        )}

        {!loading && drill.invoices.length > 0 && (
          <>
            <div style={{ fontSize: 12, color: "var(--text2)", margin: "16px 0 8px" }}>
              <strong style={{ color: "var(--green)" }}>{matched.length}</strong> match the rule
              {disagreeing.length > 0 && (
                <>
                  {" · "}
                  <strong style={{ color: "var(--red)" }}>{disagreeing.length}</strong> disagree (different GL)
                </>
              )}
            </div>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ fontSize: 10, color: "var(--text3)", textAlign: "left" }}>
                  <th style={{ padding: "6px 4px", borderBottom: "1px solid var(--border2)" }}>Invoice</th>
                  <th style={{ padding: "6px 4px", borderBottom: "1px solid var(--border2)" }}>Date</th>
                  <th style={{ padding: "6px 4px", borderBottom: "1px solid var(--border2)" }}>Amount</th>
                  <th style={{ padding: "6px 4px", borderBottom: "1px solid var(--border2)" }}>GL</th>
                  <th style={{ padding: "6px 4px", borderBottom: "1px solid var(--border2)" }}></th>
                </tr>
              </thead>
              <tbody>
                {disagreeing.map((inv) => (
                  <tr key={inv.invoice_id} style={{ borderBottom: "1px solid var(--border2)", background: "rgba(220, 53, 69, 0.04)" }}>
                    <td className="mono" style={{ padding: "6px 4px", color: "var(--gold-dark)" }}>{inv.invoice_id}</td>
                    <td style={{ padding: "6px 4px", color: "var(--text3)" }}>{inv.invoice_date ?? "—"}</td>
                    <td className="mono" style={{ padding: "6px 4px" }}>€{inv.amount.toLocaleString()}</td>
                    <td className="mono" style={{ padding: "6px 4px" }}>{inv.gl_code}</td>
                    <td style={{ padding: "6px 4px" }}><span className="badge badge-red" style={{ fontSize: 10 }}>disagrees</span></td>
                  </tr>
                ))}
                {matched.slice(0, 10).map((inv) => (
                  <tr key={inv.invoice_id} style={{ borderBottom: "1px solid var(--border2)" }}>
                    <td className="mono" style={{ padding: "6px 4px", color: "var(--gold-dark)" }}>{inv.invoice_id}</td>
                    <td style={{ padding: "6px 4px", color: "var(--text3)" }}>{inv.invoice_date ?? "—"}</td>
                    <td className="mono" style={{ padding: "6px 4px" }}>€{inv.amount.toLocaleString()}</td>
                    <td className="mono" style={{ padding: "6px 4px" }}>{inv.gl_code}</td>
                    <td style={{ padding: "6px 4px" }}><span className="badge badge-green" style={{ fontSize: 10 }}>matches</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {matched.length > 10 && <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 8 }}>... and {matched.length - 10} more matching invoices</div>}
          </>
        )}
      </div>
    </div>
  );
}
