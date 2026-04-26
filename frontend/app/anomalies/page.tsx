"use client";

import { useState, useEffect } from "react";
import Nav from "@/components/shell/Nav";
import { useCustomer } from "@/lib/customer-context";
import ErrorState from "@/components/shell/ErrorState";
import TopBar from "@/components/shell/TopBar";
import AitoPanel from "@/components/shell/AitoPanel";
import { apiFetch, fmtAmount } from "@/lib/api";
import type { AitoPanelConfig } from "@/lib/types";

const PANEL: AitoPanelConfig = {
  operation: "_predict (inverse)",
  stats: [
    { value: "Inverse", label: "Approach" },
    { value: "Live", label: "Predictions" },
    { value: "$invoices", label: "Records" },
    { value: "Zero", label: "Training" },
  ],
  description:
    'Anomaly detection uses inverse prediction: low <code style="font-size:11px;color:var(--aito-accent)">$p</code> on predictable fields = anomaly signal. ' +
    "No separate anomaly model needed \u2014 same _predict engine.",
  query: JSON.stringify(
    { from: "invoices", where: { vendor: "Brand New Corp", amount: 45000 }, predict: "gl_code", select: ["$p", "feature", "$why"] },
    null, 2,
  ),
  links: [
    { label: "API reference: _predict", url: "https://aito.ai/docs/api/#post-api-v1-predict" },
  ],
};

interface AnomalyFlag {
  invoice_id: string;
  vendor: string;
  amount: number;
  title: string;
  description: string;
  recommendation: string;
  category: string;
  anomaly_score: number;
  severity: "high" | "medium" | "low";
}

interface AnomalyResponse {
  flags: AnomalyFlag[];
  metrics: { total: number; high: number; medium: number; low: number; scanned: number };
}

const SEVERITY_BADGE: Record<string, React.ReactNode> = {
  high: <span className="badge badge-red">High</span>,
  medium: <span className="badge badge-amber">Medium</span>,
  low: <span className="badge badge-gold">Low</span>,
};

export default function AnomaliesPage() {
  const { customerId } = useCustomer();
  const [data, setData] = useState<AnomalyResponse | null>(null);
  const [live, setLive] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    setData(null); setLive(false); setError(false);
    apiFetch<AnomalyResponse>(`/api/anomalies/scan?customer_id=${customerId}`)
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
          title="Anomaly Detection"
          subtitle={m ? `${m.high} high \u00B7 ${m.medium} medium \u00B7 ${m.low} low \u00B7 scanned ${m.scanned} invoices` : error ? "Backend not reachable" : "Loading..."}
          live={live}
        />
        <div className="content">
          <div className="metrics">
            <div className="metric highlight"><div className="metric-label">Anomalies found</div><div className="metric-value">{m?.total ?? "--"}</div></div>
            <div className="metric"><div className="metric-label">High priority</div><div className="metric-value" style={{ color: "var(--red)" }}>{m?.high ?? "--"}</div></div>
            <div className="metric"><div className="metric-label">Medium</div><div className="metric-value">{m?.medium ?? "--"}</div></div>
            <div className="metric"><div className="metric-label">Scanned</div><div className="metric-value">{m?.scanned ?? "--"}</div></div>
          </div>
          <div className="card">
            <div className="card-header"><span className="card-title">Flagged transactions</span><span className="card-hint">Inverse <code>_predict</code> &middot; reasons and recommended action shown</span></div>
            {(data?.flags ?? []).map((f, i) => (
              <div key={i} className="anomaly-row" style={{ alignItems: "flex-start" }}>
                <div className={`anomaly-icon ${f.severity}`}>
                  {f.severity === "high" ? (
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 2L1 12h12L7 2z" stroke="#8b1a1a" strokeWidth="1.3"/><path d="M7 6v3M7 10.5v.5" stroke="#8b1a1a" strokeWidth="1.3" strokeLinecap="round"/></svg>
                  ) : (
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="5.5" stroke="#92610a" strokeWidth="1.3"/><path d="M7 4.5v3M7 9v.5" stroke="#92610a" strokeWidth="1.3" strokeLinecap="round"/></svg>
                  )}
                </div>
                <div className="anomaly-body">
                  <div className="anomaly-title">{f.title}</div>
                  <div className="anomaly-sub">{f.description}</div>
                  {f.recommendation && (
                    <div style={{ marginTop: 6, padding: "6px 10px", background: "var(--surface2)", borderLeft: "3px solid var(--gold-mid)", borderRadius: 3, fontSize: "11.5px", color: "var(--text2)" }}>
                      <strong style={{ color: "var(--gold-dark)", marginRight: 6 }}>Recommended:</strong>
                      {f.recommendation}
                    </div>
                  )}
                </div>
                <div>{SEVERITY_BADGE[f.severity]}</div>
                <div className="anomaly-amount" style={{ marginLeft: 16 }}>{fmtAmount(f.amount)}</div>
              </div>
            ))}
            {!data && !error && Array.from({ length: 5 }).map((_, i) => (
              <div key={`skel-${i}`} style={{ display: "flex", alignItems: "center", padding: 16, borderBottom: "1px solid var(--border2)", gap: 16 }}>
                <div className="skeleton" style={{ width: 14, height: 14, borderRadius: "50%" }} />
                <div style={{ flex: 1 }}>
                  <div className="skeleton" style={{ height: 14, width: "60%", marginBottom: 6 }} />
                  <div className="skeleton" style={{ height: 11, width: "85%" }} />
                </div>
                <div className="skeleton" style={{ height: 18, width: 60, borderRadius: 12 }} />
                <div className="skeleton" style={{ height: 14, width: 80 }} />
              </div>
            ))}
            {data && data.flags.length === 0 && (
              <div style={{ padding: 32, textAlign: "center", color: "var(--text3)", fontSize: 13, lineHeight: 1.6 }}>
                No anomalies detected — every invoice fits a known pattern.
                <br />
                <span style={{ fontSize: 11 }}>Try a smaller customer with less history to see cold-start anomaly behavior.</span>
              </div>
            )}
          </div>
        </div>
      </div>
      <AitoPanel config={PANEL} />
    </>
  );
}
