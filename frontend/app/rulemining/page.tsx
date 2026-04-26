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
  operation: "_relate",
  stats: [
    { value: "30", label: "Patterns" },
    { value: "25", label: "Strong" },
    { value: "$invoices", label: "Records" },
    { value: "Zero", label: "Training" },
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
};

interface RuleCandidate {
  pattern: string;
  target: string;
  support: string;
  support_ratio: number;
  coverage: number;
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

export default function RuleMiningPage() {
  const { customerId } = useCustomer();
  const [data, setData] = useState<RulesResponse | null>(null);
  const [live, setLive] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    setData(null); setLive(false); setError(false);
    apiFetch<RulesResponse>(`/api/rules/candidates?customer_id=${customerId}`)
      .then((d) => { setData(d); setLive(true); })
      .catch(() => setError(true));
  }, [customerId]);

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
              <div key={i} className="rule-row">
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="rule-pattern">{c.pattern}</div>
                  <div className="rule-arrow" style={{ marginTop: 3, fontSize: 11, color: "var(--text3)" }}>&rarr; {c.target}</div>
                </div>
                <div className={`rule-support ${supportClass(c.support_ratio)}`} style={{ minWidth: 80, textAlign: "right" }}>{c.support}</div>
                <div style={{ fontSize: 12, fontFamily: "'IBM Plex Mono', monospace", color: "var(--text2)", minWidth: 80, textAlign: "right" }}>{c.coverage}%</div>
                <div style={{ textAlign: "center" }}>{strengthBadge(c.strength)}</div>
                <div style={{ minWidth: 100, textAlign: "right" }}>
                  {c.strength === "strong" && <span style={{ fontSize: 11, color: "var(--text3)", fontStyle: "italic" }}>candidate</span>}
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
    </>
  );
}
