"use client";

import { useState, useEffect } from "react";
import Nav from "@/components/shell/Nav";
import TopBar from "@/components/shell/TopBar";
import AitoPanel from "@/components/shell/AitoPanel";
import ConfidenceBar from "@/components/prediction/ConfidenceBar";
import { apiFetch, fmtAmount } from "@/lib/api";
import type { AitoPanelConfig } from "@/lib/types";

const PANEL: AitoPanelConfig = {
  operation: "_match",
  stats: [
    { value: "0.91", label: "Avg confidence" },
    { value: "18ms", label: "Response" },
    { value: "120", label: "Bank txns" },
    { value: "Zero", label: "Training" },
  ],
  description:
    'Invoice-to-bank matching uses <code style="font-size:11px;color:var(--aito-accent)">_match</code> to traverse the schema link from bank_transactions to invoices. ' +
    "Aito finds which invoices associate with each bank description and amount.",
  query: JSON.stringify(
    { from: "bank_transactions", where: { description: "KESKO OYJ", amount: 4220 }, match: "invoice_id", limit: 3 },
    null, 2,
  ),
  links: [
    { label: "API reference: _match", url: "https://aito.ai/docs/api/#post-api-v1-match" },
  ],
};

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

export default function MatchingPage() {
  const [data, setData] = useState<MatchResponse | null>(null);
  const [live, setLive] = useState(false);

  useEffect(() => {
    apiFetch<MatchResponse>("/api/matching/pairs")
      .then((d) => { setData(d); setLive(true); })
      .catch(() => {});
  }, []);

  const m = data?.metrics;

  return (
    <>
      <Nav />
      <div className="main">
        <TopBar
          breadcrumb="Payables"
          title="Payment Matching"
          subtitle={m ? `${m.total} invoices \u00B7 ${m.matched} matched \u00B7 ${m.suggested} suggested \u00B7 ${m.unmatched} unmatched` : "Loading..."}
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
            <div className="card-header"><span className="card-title">Invoice &#x2194; Bank transaction matching</span><span className="card-hint">Aito _match traverses schema links</span></div>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ padding: "10px 20px", fontSize: "10.5px", fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", background: "var(--surface2)", borderBottom: "1px solid var(--border2)", textAlign: "left" }}>Open invoices</th>
                  <th style={{ width: 80, background: "var(--surface2)", borderBottom: "1px solid var(--border2)", borderLeft: "1px solid var(--border2)", borderRight: "1px solid var(--border2)" }} />
                  <th style={{ padding: "10px 20px", fontSize: "10.5px", fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", background: "var(--surface2)", borderBottom: "1px solid var(--border2)", textAlign: "left" }}>Bank transactions</th>
                </tr>
              </thead>
              <tbody>
                {(data?.pairs ?? []).map((p) => {
                  const rowClass = p.status === "matched" ? "matched" : p.status === "suggested" ? "suggested" : "";
                  return (
                    <tr key={p.invoice_id}>
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
