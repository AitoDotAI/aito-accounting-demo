"use client";

import React, { useState, useEffect } from "react";
import Nav from "@/components/shell/Nav";
import { useCustomer } from "@/lib/customer-context";
import ErrorState from "@/components/shell/ErrorState";
import TopBar from "@/components/shell/TopBar";
import AitoPanel from "@/components/shell/AitoPanel";
import ConfidenceBar from "@/components/prediction/ConfidenceBar";
import WhyCards from "@/components/prediction/WhyCards";
import { apiFetch, fmtAmount } from "@/lib/api";
import type { AitoPanelConfig } from "@/lib/types";

const PANEL: AitoPanelConfig = {
  source: [
    { label: "Payment matching", path: "src/matching_service.py" },
    { label: "Reference lookup (no Aito)", path: "src/reference_lookup.py" },
    { label: "This page", path: "frontend/app/matching/page.tsx" },
    { label: "Aito v2 client", path: "src/aito_v2_client.py" },
  ],
  operation: "_predict",
  stats: [
    { value: "_predict", label: "Operation" },
    { value: "Live", label: "Predictions" },
    { value: "$invoices", label: "Invoices" },
    { value: "Indexed", label: "Model" },
  ],
  description:
    '<code style="font-size:11px;color:var(--aito-accent)">_predict invoice_id</code> traverses the schema link from bank_transactions to invoices, returning full invoice rows ranked by association. ' +
    "A payment that quotes its invoice's reference is matched by lookup first; only the ones without a reference reach Aito, " +
    "which matches on the payer's name, description text and amount.",
  query: JSON.stringify(
    { from: "bank_transactions", where: { description: "KESKO OYJ HELSINKI", amount: 4220 }, predict: "invoice_id", select: ["$p", "invoice_id", "vendor", "amount", "$why"] },
    null, 2,
  ),
  links: [
    { label: "API reference: _predict", url: "https://aito.ai/docs/api/#post-api-v1-predict" },
  ],
  flow_steps: [
    { n: 1, produces: "Incoming payments", call: "_search bank_transactions WHERE customer_id LIMIT 40; show 6 without a reference, 2 with" },
    { n: 2, produces: "Open ledger", call: "_search invoices WHERE customer_id (the payments' invoices + 30 others)" },
    { n: 3, produces: "Matched by reference", call: "No Aito call: the bank line quotes an open invoice's reference" },
    { n: 4, produces: "Best matching invoice for the rest", call: "_predict invoice_id WHERE customer_id, description, vendor_name, amount" },
    { n: 5, produces: "$why explanation per Aito match", call: "Same _predict, select [$p, $why]; expanded on click" },
  ],
};

interface MatchExplanation {
  factor: string;
  detail: string;
  signal: "strong" | "partial" | "weak";
}

import type { WhyFactor } from "@/lib/types";

interface MatchPair {
  /** Aito's own $p for this invoice, before the amount-proximity blend.
   *  The $why chain decomposes THIS, not `confidence`. */
  model_p?: number;
  invoice_id: string;
  invoice_vendor: string;
  invoice_amount: number;
  bank_txn_id: string | null;
  bank_description: string | null;
  bank_amount: number | null;
  bank_name: string | null;
  confidence: number;
  status: "matched" | "suggested" | "unmatched";
  /** "reference": the bank line quoted the invoice's reference, no prediction made. */
  matched_by: "reference" | "aito" | null;
  /** $why factors in the same grouped shape as invoice predictions. */
  explanation?: WhyFactor[];
}

interface MatchResponse {
  pairs: MatchPair[];
  metrics: {
    matched: number; suggested: number; unmatched: number; total: number; ledger_size?: number;
    matched_by_reference: number; matched_by_aito: number;
    /** Over Aito's matches only; a lookup's certainty is not the model's. */
    avg_confidence: number; match_rate: number;
  };
}

function connectorBadge(pair: MatchPair) {
  if (pair.matched_by === "reference") {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
        <div style={{ height: 3, width: 48, background: "var(--border)", borderRadius: 2 }} />
        <span className="badge badge-gray" style={{ fontSize: 10 }}>ref</span>
      </div>
    );
  }
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
  const [error, setError] = useState<Error | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    setData(null); setLive(false); setError(null); setExpanded(null);
    apiFetch<MatchResponse>(`/api/matching/pairs?customer_id=${customerId}`)
      .then((d) => {
        setData(d); setLive(true);
        // Auto-expand the first matched row so users discover the "why" feature
        const firstMatched = d.pairs.find((p) => p.status === "matched" && p.explanation && p.explanation.length > 0);
        if (firstMatched) setExpanded(firstMatched.bank_txn_id);
      })
      .catch((e) => setError(e));
  }, [customerId]);

  const m = data?.metrics;

  return (
    <>
      <Nav />
      <div className="main">
        <TopBar
          breadcrumb="Payables"
          title="Payment Matching"
          subtitle={m ? `${m.total} payments \u00B7 open ledger of ${m.ledger_size ?? "?"}` : error ? "Backend not reachable" : "Loading..."}
          live={live}
        />
        <div className="content">
          <div className="metrics">
            <div className="metric highlight"><div className="metric-label">Matched by Aito</div><div className="metric-value">{m?.matched_by_aito ?? "--"}</div></div>
            <div className="metric"><div className="metric-label">Avg Aito Confidence</div><div className="metric-value">{m?.avg_confidence.toFixed(2) ?? "--"}</div></div>
            <div className="metric"><div className="metric-label">Matched by Reference</div><div className="metric-value">{m?.matched_by_reference ?? "--"}</div></div>
            <div className="metric"><div className="metric-label">Unmatched</div><div className="metric-value">{m?.unmatched ?? "--"}</div></div>
          </div>
          <div className="card">
            <div className="card-header"><span className="card-title">Incoming payment &#x2192; Open invoice</span><span className="card-hint">Payments without a reference first &middot; click an Aito match to see why</span></div>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ padding: "10px 20px", fontSize: "10.5px", fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", background: "var(--surface2)", borderBottom: "1px solid var(--border2)", textAlign: "left" }}>Incoming payment (bank)</th>
                  <th style={{ width: 80, background: "var(--surface2)", borderBottom: "1px solid var(--border2)", borderLeft: "1px solid var(--border2)", borderRight: "1px solid var(--border2)" }} />
                  <th style={{ padding: "10px 20px", fontSize: "10.5px", fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", background: "var(--surface2)", borderBottom: "1px solid var(--border2)", textAlign: "left" }}>Assigned open invoice</th>
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
                  const rowKey = p.bank_txn_id ?? p.invoice_id;
                  const isExpanded = expanded === rowKey;
                  const hasExplanation = p.explanation && p.explanation.length > 0;
                  return (
                    <React.Fragment key={rowKey}>
                    <tr
                      onClick={() => hasExplanation && setExpanded(isExpanded ? null : rowKey)}
                      style={{ cursor: hasExplanation ? "pointer" : "default" }}
                    >
                      {/* Payment on the left: it is the thing arriving, and
                          the thing being assigned. Reading order is the
                          direction of the decision. */}
                      <td className={`match-item ${rowClass}`} style={{ verticalAlign: "middle" }}>
                        <div className="match-name">{p.bank_description}</div>
                        <div className="match-detail">{fmtAmount(p.bank_amount!)} &middot; {p.bank_name}</div>
                      </td>
                      <td style={{ textAlign: "center", verticalAlign: "middle", borderLeft: "1px solid var(--border2)", borderRight: "1px solid var(--border2)", borderBottom: "1px solid var(--border2)" }}>
                        {connectorBadge(p)}
                      </td>
                      <td className={`match-item ${rowClass}`} style={{ verticalAlign: "middle" }}>
                        {p.invoice_id ? (
                          <>
                            <div className="match-name">{p.invoice_vendor} &middot; {p.invoice_id}</div>
                            <div className="match-detail">
                              {fmtAmount(p.invoice_amount)}
                              {p.matched_by === "reference" && <> &middot; matched by reference, no prediction needed</>}
                              {/* The reference settles WHICH invoice, not whether it is paid in
                                  full: a short or over payment still needs the clerk's eye. */}
                              {p.bank_amount != null && Math.abs(p.bank_amount - p.invoice_amount) >= 0.005 && (
                                <span style={{ color: "var(--amber)" }}>
                                  {" "}&middot; {p.bank_amount > p.invoice_amount ? "overpaid" : "underpaid"}{" "}
                                  {fmtAmount(Math.abs(p.bank_amount - p.invoice_amount))}
                                </span>
                              )}
                            </div>
                          </>
                        ) : (
                          <div className="match-name" style={{ color: "var(--text3)" }}>No invoice matched</div>
                        )}
                      </td>
                    </tr>
                    {isExpanded && p.explanation && p.explanation.length > 0 && (
                      <tr>
                        <td colSpan={3} style={{ padding: "0 20px 12px", background: "var(--surface2)" }}>
                          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--gold-dark)", marginBottom: 6, marginTop: 8 }}>
                            Why this match?
                          </div>
                          <WhyCards
                            why={p.explanation}
                            confidence={p.confidence}
                            modelP={p.model_p}
                            blendNote={"blended with how closely the amounts agree \u2192"}
                            keepFields={["amount"]}
                          />
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
