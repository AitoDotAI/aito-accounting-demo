"use client";

import { useState, useEffect } from "react";
import Nav from "@/components/shell/Nav";
import { useCustomer } from "@/lib/customer-context";
import ErrorState from "@/components/shell/ErrorState";
import TopBar from "@/components/shell/TopBar";
import AitoPanel from "@/components/shell/AitoPanel";
import GovernanceStepper from "@/components/governance/GovernanceStepper";
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
    'Conjunction rules from <code style="font-size:11px;color:var(--aito-accent)">_relate</code> with ' +
    '<code style="font-size:11px;color:var(--aito-accent)">$patterns</code>. Aito mines the AND-rules a human ' +
    "would write for each output an AP clerk codes &mdash; GL code and approver &mdash; from intake inputs only " +
    "(vendor, category, amount band). No output is used to predict another, so the rules actually fire at routing " +
    "time. Support ratios are exact historical counts, not ML estimates.",
  query: JSON.stringify(
    {
      from: { from: "invoices", where: { customer_id: "…" } },
      where: { gl_code: "1600" },
      relate: {
        $patterns: {
          $related: {
            relate: ["vendor", "category", "vendor_country", "amount_band"],
            k: 8,
            to: { gl_code: "1600" },
          },
        },
      },
    },
    null, 2,
  ),
  links: [
    { label: "API reference: _relate", url: "https://aito.ai/docs/api/#post-api-v1-relate" },
  ],
  flow_steps: [
    { n: 1, produces: "Target values to mine", call: "_search invoices WHERE customer_id; rank gl_code & approver by volume" },
    { n: 2, produces: "AND-rule candidates (discovery)", call: "_relate $patterns $related over inputs-only fields → per target value" },
    { n: 3, produces: "Exact support, coverage, lift", call: "_search counts per rule — exact, so the numbers match the drill-down" },
    { n: 4, produces: "Drill-down (matching invoices)", call: "_search invoices WHERE customer_id & every rule clause" },
  ],
};

interface RuleClause {
  field: string;
  value: string;
}

interface RuleCandidate {
  pattern: string;
  clauses: RuleClause[];
  target_field: string;   // "gl_code" | "approver" — the output the rule predicts
  target: string;         // display, e.g. "GL 1600 (Capital Equipment)" or "Liisa Virtanen"
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

// How each output field reads in the UI.
const TARGET_KIND: Record<string, string> = { gl_code: "GL code", approver: "Approver" };

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

// Render a rule's AND-conjunction as `field = "value"` terms joined by AND.
function ClauseList({ clauses }: { clauses: RuleClause[] }) {
  return (
    <>
      {clauses.map((c, i) => (
        <span key={i}>
          {i > 0 && <span style={{ color: "var(--text3)" }}> AND </span>}
          <strong>{c.field}</strong>
          {" = "}
          <code style={{ fontFamily: "'IBM Plex Mono', monospace", color: "var(--gold-dark)" }}>"{c.value}"</code>
        </span>
      ))}
    </>
  );
}

interface DrilldownInvoice {
  invoice_id: string;
  vendor: string;
  amount: number;
  gl_code: string;
  approver?: string;
  category: string;
  amount_band?: string;
  invoice_date?: string;
  target_actual?: string;  // the rule's output field value on this invoice
  matched_rule: boolean;
}

// Render a rule's right-hand side: "GL is 1600 (Capital Equipment)" or
// "approver is Liisa Virtanen".
function TargetPhrase({ candidate }: { candidate: RuleCandidate }) {
  if (candidate.target_field === "gl_code") {
    return <>GL is <strong>{candidate.target_value} ({candidate.target_label})</strong></>;
  }
  return <>approver is <strong>{candidate.target_label}</strong></>;
}

function targetChip(field: string) {
  const label = TARGET_KIND[field] ?? field;
  const color = field === "approver" ? "var(--aito-accent)" : "var(--gold-dark)";
  return (
    <span style={{
      fontSize: 9.5, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".5px",
      color, border: `1px solid ${color}`, borderRadius: 3, padding: "1px 5px", opacity: 0.85,
    }}>{label}</span>
  );
}

interface DrillCounts {
  match: number;
  total: number;
  disagree: number;
}

export default function RuleMiningPage() {
  const { customerId } = useCustomer();
  const [data, setData] = useState<RulesResponse | null>(null);
  const [live, setLive] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [drilldown, setDrilldown] = useState<{ rule: RuleCandidate; invoices: DrilldownInvoice[]; counts?: DrillCounts } | null>(null);
  const [drillLoading, setDrillLoading] = useState(false);

  useEffect(() => {
    setData(null); setLive(false); setError(null); setDrilldown(null);
    apiFetch<RulesResponse>(`/api/rules/candidates?customer_id=${customerId}`)
      .then((d) => { setData(d); setLive(true); })
      .catch((e) => setError(e));
  }, [customerId]);

  const openDrilldown = async (rule: RuleCandidate) => {
    setDrillLoading(true);
    setDrilldown({ rule, invoices: [] });
    try {
      const r = await apiFetch<{ invoices: DrilldownInvoice[]; counts?: DrillCounts }>(
        `/api/rules/drilldown?customer_id=${customerId}` +
        `&clauses=${encodeURIComponent(JSON.stringify(rule.clauses))}` +
        `&target_value=${encodeURIComponent(rule.target_value)}` +
        `&target_field=${encodeURIComponent(rule.target_field)}`
      );
      setDrilldown({ rule, invoices: r.invoices, counts: r.counts });
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
          breadcrumb="Governance · 1. Discover"
          title="Rule Mining"
          subtitle={m ? `${m.total} conjunction rules discovered via Aito _relate $patterns` : error ? "Backend not reachable" : "Loading..."}
          live={live}
        />
        <GovernanceStepper active="discover" />
        <div className="content">
          <div className="metrics">
            <div className="metric highlight"><div className="metric-label">Candidate rules</div><div className="metric-value">{m?.total ?? "--"}</div></div>
            <div className="metric"><div className="metric-label">Strong (&ge;95%)</div><div className="metric-value">{m?.strong ?? "--"}</div><div className="metric-sub metric-up">Ready to promote</div></div>
            <div className="metric"><div className="metric-label">Coverage gain</div><div className="metric-value">+{m?.coverage_gain ?? "--"}%</div></div>
            <div className="metric"><div className="metric-label">Review</div><div className="metric-value">{m?.review ?? "--"}</div></div>
          </div>
          <div className="card">
            <div className="card-header"><span className="card-title">Candidates ({m?.total ?? "..."})</span><span className="card-hint">AND-rules from Aito _relate $patterns</span></div>
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
                title="Click to list the invoices this rule fires on"
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="rule-pattern" style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
                    {targetChip(c.target_field)}
                    <span>
                      When <ClauseList clauses={c.clauses} />
                      {", "} <TargetPhrase candidate={c} />
                    </span>
                  </div>
                  <div className="rule-arrow" style={{ marginTop: 4, fontSize: 11, color: "var(--text3)" }}>
                    in {c.support_match} of {c.support_total} matching invoices
                    {c.lift > 1 && <> &middot; <LiftHint value={c.lift} /></>}
                  </div>
                </div>
                <div className={`rule-support ${supportClass(c.support_ratio)}`} style={{ minWidth: 80, textAlign: "right" }}>{Math.round(c.support_ratio * 100)}%</div>
                <div style={{ fontSize: 12, fontFamily: "'IBM Plex Mono', monospace", color: "var(--text2)", minWidth: 80, textAlign: "right" }}>{c.coverage}%</div>
                <div style={{ textAlign: "center" }}>{strengthBadge(c.strength)}</div>
                <div style={{ minWidth: 100, textAlign: "right" }}>
                  <button
                    onClick={(e) => { e.stopPropagation(); openDrilldown(c); }}
                    style={{
                      fontSize: 11, color: "var(--text3)", background: "transparent",
                      border: "none", cursor: "pointer", fontStyle: "italic",
                      fontFamily: "inherit",
                    }}
                  >
                    view invoices &rarr;
                  </button>
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
            {error && <ErrorState error={error} />}
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
  drill: { rule: RuleCandidate; invoices: DrilldownInvoice[]; counts?: DrillCounts };
  loading: boolean;
  onClose: () => void;
}) {
  const matched = drill.invoices.filter((i) => i.matched_rule);
  const disagreeing = drill.invoices.filter((i) => !i.matched_rule);
  // Exact totals from the backend (not the sample size): all exceptions
  // are fetched, matches are a sample, so prefer counts when present.
  const matchCount = drill.counts?.match ?? matched.length;
  const disagreeCount = drill.counts?.disagree ?? disagreeing.length;

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
              When <ClauseList clauses={drill.rule.clauses} />
            </div>
            <div style={{ fontSize: 13, color: "var(--text2)", marginTop: 4 }}>
              <TargetPhrase candidate={drill.rule} /> in {drill.rule.support_match} of {drill.rule.support_total} matching invoices ({Math.round(drill.rule.support_ratio * 100)}%)
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
              <strong style={{ color: "var(--green)" }}>{matchCount}</strong> match the rule
              {disagreeCount > 0 && (
                <>
                  {" · "}
                  <strong style={{ color: "var(--red)" }}>{disagreeCount}</strong> disagree (different GL)
                </>
              )}
              {drill.counts && matched.length < matchCount && (
                <span style={{ color: "var(--text3)" }}> · showing all exceptions + a sample of matches</span>
              )}
            </div>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ fontSize: 10, color: "var(--text3)", textAlign: "left" }}>
                  <th style={{ padding: "6px 4px", borderBottom: "1px solid var(--border2)" }}>Invoice</th>
                  <th style={{ padding: "6px 4px", borderBottom: "1px solid var(--border2)" }}>Date</th>
                  <th style={{ padding: "6px 4px", borderBottom: "1px solid var(--border2)" }}>Amount</th>
                  <th style={{ padding: "6px 4px", borderBottom: "1px solid var(--border2)" }}>{TARGET_KIND[drill.rule.target_field] ?? "Output"}</th>
                  <th style={{ padding: "6px 4px", borderBottom: "1px solid var(--border2)" }}></th>
                </tr>
              </thead>
              <tbody>
                {disagreeing.map((inv) => (
                  <tr key={inv.invoice_id} style={{ borderBottom: "1px solid var(--border2)", background: "rgba(220, 53, 69, 0.04)" }}>
                    <td className="mono" style={{ padding: "6px 4px", color: "var(--gold-dark)" }}>{inv.invoice_id}</td>
                    <td style={{ padding: "6px 4px", color: "var(--text3)" }}>{inv.invoice_date ?? "—"}</td>
                    <td className="mono" style={{ padding: "6px 4px" }}>€{inv.amount.toLocaleString()}</td>
                    <td className="mono" style={{ padding: "6px 4px" }}>{inv.target_actual ?? inv.gl_code}</td>
                    <td style={{ padding: "6px 4px" }}><span className="badge badge-red" style={{ fontSize: 10 }}>disagrees</span></td>
                  </tr>
                ))}
                {matched.slice(0, 10).map((inv) => (
                  <tr key={inv.invoice_id} style={{ borderBottom: "1px solid var(--border2)" }}>
                    <td className="mono" style={{ padding: "6px 4px", color: "var(--gold-dark)" }}>{inv.invoice_id}</td>
                    <td style={{ padding: "6px 4px", color: "var(--text3)" }}>{inv.invoice_date ?? "—"}</td>
                    <td className="mono" style={{ padding: "6px 4px" }}>€{inv.amount.toLocaleString()}</td>
                    <td className="mono" style={{ padding: "6px 4px" }}>{inv.target_actual ?? inv.gl_code}</td>
                    <td style={{ padding: "6px 4px" }}><span className="badge badge-green" style={{ fontSize: 10 }}>matches</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {matchCount > 10 && <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 8 }}>... and {matchCount - Math.min(matched.length, 10)} more matching invoices</div>}
          </>
        )}
      </div>
    </div>
  );
}
