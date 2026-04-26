"use client";

import React, { useState, useEffect } from "react";
import Nav from "@/components/shell/Nav";
import { useCustomer } from "@/lib/customer-context";
import ErrorState from "@/components/shell/ErrorState";
import TopBar from "@/components/shell/TopBar";
import AitoPanel from "@/components/shell/AitoPanel";
import ConfidenceBar from "@/components/prediction/ConfidenceBar";
import { apiFetch, fmtAmount } from "@/lib/api";
import type { AitoPanelConfig } from "@/lib/types";

const PANEL: AitoPanelConfig = {
  operation: "_predict",
  stats: [
    { value: "_predict", label: "Operation" },
    { value: "Live", label: "Predictions" },
    { value: "$invoices", label: "Invoices" },
    { value: "Zero", label: "Training" },
  ],
  description:
    '<code style="font-size:11px;color:var(--aito-accent)">_predict invoice_id</code> traverses the schema link from bank_transactions to invoices, returning full invoice rows ranked by association. ' +
    "Aito matches description text tokens and amount to find the most likely invoice.",
  query: JSON.stringify(
    { from: "bank_transactions", where: { description: "KESKO OYJ HELSINKI", amount: 4220 }, predict: "invoice_id", select: ["$p", "invoice_id", "vendor", "amount", "$why"] },
    null, 2,
  ),
  links: [
    { label: "API reference: _predict", url: "https://aito.ai/docs/api/#post-api-v1-predict" },
  ],
};

interface MatchExplanation {
  factor: string;
  detail: string;
  signal: "strong" | "partial" | "weak";
}

interface MatchPair {
  invoice_id: string;
  invoice_vendor: string;
  invoice_amount: number;
  bank_txn_id: string | null;
  bank_description: string | null;
  bank_amount: number | null;
  bank_name: string | null;
  confidence: number;
  status: "matched" | "suggested" | "unmatched";
  explanation?: MatchExplanation[];
}

interface MatchResponse {
  pairs: MatchPair[];
  metrics: { matched: number; suggested: number; unmatched: number; total: number; avg_confidence: number; match_rate: number };
}

function connectorBadge(pair: MatchPair) {
  if (pair.status === "matched" || pair.status === "suggested") {
    const color = pair.status === "matched" ? "#6ab87a" : "var(--gold-mid)";
    const badgeClass = pair.status === "matched" ? "badge badge-green" : "badge badge-gold";
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
        <div style={{ height: 3, width: 48, background: color, borderRadius: 2 }} />
        <span className={badgeClass} style={{ fontSize: 10 }}>{pair.confidence.toFixed(2)}</span>
      </div>
    );
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
      <div style={{ height: 0, width: 44, borderTop: "2px dashed var(--border)" }} />
      <span style={{ fontSize: 10, color: "var(--text3)" }}>&mdash;</span>
    </div>
  );
}

const SIGNAL_COLOR: Record<string, string> = { strong: "var(--green)", partial: "var(--amber)", weak: "var(--red)" };

export default function MatchingPage() {
  const { customerId } = useCustomer();
  const [data, setData] = useState<MatchResponse | null>(null);
  const [live, setLive] = useState(false);
  const [error, setError] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    setData(null); setLive(false); setError(false);
    apiFetch<MatchResponse>(`/api/matching/pairs?customer_id=${customerId}`)
      .then((d) => { setData(d); setLive(true); })
      .catch(() => setError(true));
  }, [customerId]);

  const m = data?.metrics;

  return (
    <>
      <Nav />
      <div className="main">
        <TopBar
          breadcrumb="Payables"
          title="Payment Matching"
          subtitle={m ? `${m.total} invoices \u00B7 ${m.matched} matched \u00B7 ${m.suggested} suggested \u00B7 ${m.unmatched} unmatched` : error ? "Backend not reachable" : "Loading..."}
          live={live}
        />
        <div className="content">
          <div className="metrics">
            <div className="metric highlight"><div className="metric-label">Match Rate</div><div className="metric-value">{m ? `${Math.round(m.match_rate * 100)}%` : "--"}</div></div>
            <div className="metric"><div className="metric-label">Avg Confidence</div><div className="metric-value">{m?.avg_confidence.toFixed(2) ?? "--"}</div></div>
            <div className="metric"><div className="metric-label">Matched</div><div className="metric-value">{m ? m.matched + m.suggested : "--"}</div></div>
            <div className="metric"><div className="metric-label">Unmatched</div><div className="metric-value">{m?.unmatched ?? "--"}</div></div>
          </div>
          <div className="card">
            <div className="card-header"><span className="card-title">Invoice &#x2194; Bank transaction matching</span><span className="card-hint">Click a match to see why &middot; Aito _predict invoice_id via schema link</span></div>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ padding: "10px 20px", fontSize: "10.5px", fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", background: "var(--surface2)", borderBottom: "1px solid var(--border2)", textAlign: "left" }}>Open invoices</th>
                  <th style={{ width: 80, background: "var(--surface2)", borderBottom: "1px solid var(--border2)", borderLeft: "1px solid var(--border2)", borderRight: "1px solid var(--border2)" }} />
                  <th style={{ padding: "10px 20px", fontSize: "10.5px", fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", background: "var(--surface2)", borderBottom: "1px solid var(--border2)", textAlign: "left" }}>Bank transactions</th>
                </tr>
              </thead>
              <tbody>
                {!data && !error && Array.from({ length: 6 }).map((_, i) => (
                  <tr key={`skel-${i}`}>
                    <td style={{ padding: "12px 20px" }}>
                      <div className="skeleton" style={{ height: 14, width: "75%", marginBottom: 6 }} />
                      <div className="skeleton" style={{ height: 11, width: "40%" }} />
                    </td>
                    <td style={{ textAlign: "center", borderLeft: "1px solid var(--border2)", borderRight: "1px solid var(--border2)" }}>
                      <div className="skeleton" style={{ height: 18, width: 18, borderRadius: "50%", margin: "0 auto" }} />
                    </td>
                    <td style={{ padding: "12px 20px" }}>
                      <div className="skeleton" style={{ height: 14, width: "65%", marginBottom: 6 }} />
                      <div className="skeleton" style={{ height: 11, width: "35%" }} />
                    </td>
                  </tr>
                ))}
                {(data?.pairs ?? []).map((p) => {
                  const rowClass = p.status === "matched" ? "matched" : p.status === "suggested" ? "suggested" : "";
                  const isExpanded = expanded === p.invoice_id;
                  const hasExplanation = p.explanation && p.explanation.length > 0;
                  return (
                    <React.Fragment key={p.invoice_id}>
                    <tr
                      onClick={() => hasExplanation && setExpanded(isExpanded ? null : p.invoice_id)}
                      style={{ cursor: hasExplanation ? "pointer" : "default" }}
                    >
                      <td className={`match-item ${rowClass}`} style={{ verticalAlign: "middle" }}>
                        <div className="match-name">{p.invoice_vendor} &middot; {p.invoice_id}</div>
                        <div className="match-detail">{fmtAmount(p.invoice_amount)}</div>
                      </td>
                      <td style={{ textAlign: "center", verticalAlign: "middle", borderLeft: "1px solid var(--border2)", borderRight: "1px solid var(--border2)", borderBottom: "1px solid var(--border2)" }}>
                        {connectorBadge(p)}
                      </td>
                      <td className={`match-item ${rowClass}`} style={{ verticalAlign: "middle" }}>
                        {p.bank_txn_id ? (
                          <><div className="match-name">{p.bank_description}</div><div className="match-detail">{fmtAmount(p.bank_amount!)} &middot; {p.bank_name}</div></>
                        ) : (
                          <div className="match-name" style={{ color: "var(--text3)" }}>No match found</div>
                        )}
                      </td>
                    </tr>
                    {isExpanded && p.explanation && (
                      <tr>
                        <td colSpan={3} style={{ padding: "0 20px 12px", background: "var(--surface2)" }}>
                          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--gold-dark)", marginBottom: 6, marginTop: 8 }}>Why this match?</div>
                          {p.explanation.map((e, i) => (
                            <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 8px", background: "var(--surface)", borderRadius: 4, marginBottom: 3, fontSize: 12 }}>
                              <span style={{ width: 8, height: 8, borderRadius: "50%", background: SIGNAL_COLOR[e.signal], flexShrink: 0 }} />
                              <span style={{ fontWeight: 500, minWidth: 90, color: "var(--text2)" }}>{e.factor}</span>
                              <span style={{ color: "var(--text3)" }}>{e.detail}</span>
                            </div>
                          ))}
                        </td>
                      </tr>
                    )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      <AitoPanel config={PANEL} />
    </>
  );
}
