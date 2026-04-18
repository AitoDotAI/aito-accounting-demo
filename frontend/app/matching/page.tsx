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
  if (pair.status === "matched")
    return <><div style={{ height: 1, width: 44, background: "#6ab87a" }} /><span className="badge badge-green" style={{ fontSize: 10 }}>{pair.confidence.toFixed(2)}</span></>;
  if (pair.status === "suggested")
    return <><div style={{ height: 1, width: 44, background: "var(--gold-mid)" }} /><span className="badge badge-gold" style={{ fontSize: 10 }}>{pair.confidence.toFixed(2)}</span></>;
  return <><div style={{ height: 1, width: 44, background: "var(--border)", borderTop: "1px dashed var(--text3)" }} /><span style={{ fontSize: 10, color: "var(--text3)" }}>&mdash;</span></>;
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
            <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr" }}>
              <div>
                <div style={{ padding: "10px 20px", fontSize: "10.5px", fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", background: "var(--surface2)", borderBottom: "1px solid var(--border2)" }}>Open invoices</div>
                {(data?.pairs ?? []).map((p) => (
                  <div key={p.invoice_id} className={`match-item ${p.status === "matched" ? "matched" : p.status === "suggested" ? "suggested" : ""}`}>
                    <div className="match-name">{p.invoice_vendor} &middot; {p.invoice_id}</div>
                    <div className="match-detail">{fmtAmount(p.invoice_amount)}</div>
                  </div>
                ))}
              </div>
              <div style={{ width: 80, display: "flex", flexDirection: "column", alignItems: "center", paddingTop: 10, borderLeft: "1px solid var(--border2)", borderRight: "1px solid var(--border2)" }}>
                {(data?.pairs ?? []).map((p) => (
                  <div key={p.invoice_id} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4, padding: "14px 0" }}>
                    {connectorBadge(p)}
                  </div>
                ))}
              </div>
              <div>
                <div style={{ padding: "10px 20px", fontSize: "10.5px", fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", background: "var(--surface2)", borderBottom: "1px solid var(--border2)" }}>Bank transactions</div>
                {(data?.pairs ?? []).map((p) => (
                  <div key={p.invoice_id} className={`match-item ${p.status === "matched" ? "matched" : p.status === "suggested" ? "suggested" : ""}`}>
                    {p.bank_txn_id ? (
                      <><div className="match-name">{p.bank_description}</div><div className="match-detail">{fmtAmount(p.bank_amount!)} &middot; {p.bank_name}</div></>
                    ) : (
                      <div className="match-name" style={{ color: "var(--text3)" }}>No match found</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
      <AitoPanel config={PANEL} />
    </>
  );
}
