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
import type { AitoPanelConfig, WhyFactor } from "@/lib/types";

const PANEL: AitoPanelConfig = {
  operation: "_predict",
  stats: [
    { value: "_predict", label: "Operation" },
    { value: "gl_code", label: "Target" },
    { value: "No invoice", label: "Input" },
    { value: "Indexed", label: "Model" },
  ],
  description:
    'These lines settle no invoice — bank charges, card settlements, direct debits, tax, payroll. ' +
    '<code style="font-size:11px;color:var(--aito-accent)">_predict gl_code</code> codes them from how this tenant coded similar lines before. ' +
    "<code>amount_band</code> rides along with the amount because Aito conditions on a band, not a raw Decimal — without it the same counterparty gets its most common code whatever the size.",
  query: JSON.stringify(
    {
      from: "bank_transactions",
      where: { customer_id: "CUST-0000", description: "KORTTIMAKSUT TILITYS  19.04.25", amount: 4703.86, amount_band: "medium" },
      predict: "gl_code",
      select: ["$value", "$p", "$why"],
    },
    null, 2,
  ),
  links: [
    { label: "API reference: _predict", url: "https://aito.ai/docs/api/#post-api-v1-predict" },
  ],
  flow_steps: [
    { n: 1, produces: "Lines with no invoice", call: "_search bank_transactions WHERE customer_id, invoice_id: null" },
    { n: 2, produces: "Proposed GL code per line", call: "_predict gl_code WHERE description, amount, amount_band" },
    { n: 3, produces: "Alternatives + $why", call: "Same _predict, select [$value, $p, $why], limit 12" },
  ],
};

interface CodedLine {
  txn_id: string;
  description: string;
  amount: number;
  bank: string;
  gl_code: string;
  gl_label: string;
  confidence: number;
  status: string;
  explanation: WhyFactor[];
  alternatives: { gl_code: string; gl_label: string; p: number }[];
}

interface Feed {
  lines: CodedLine[];
  metrics: {
    total: number; coded: number; needs_review: number;
    avg_confidence: number; automation_rate: number;
  };
}

export default function BankFeedPage() {
  const { customerId } = useCustomer();
  const [data, setData] = useState<Feed | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    apiFetch<Feed>(`/api/bankfeed/lines?customer_id=${customerId}`)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [customerId]);

  const m = data?.metrics;

  return (
    <>
      <Nav />
      <main style={{ padding: "0 0 40px" }}>
        <TopBar
          breadcrumb="Accounts Payable / Bank Feed"
          title="Bank Feed"
          subtitle={
            loading ? "Coding…"
              : m ? `${m.coded}/${m.total} coded automatically · avg ${(m.avg_confidence * 100).toFixed(0)}% confidence`
              : "Lines that settle no invoice"
          }
        />

        {error && <ErrorState message={error} />}

        {!error && data && data.lines.length === 0 && (
          <div style={{ padding: 20, color: "var(--text2)", fontSize: 13 }}>
            No un-invoiced lines in this tenant&rsquo;s feed.
          </div>
        )}

        {!error && data && data.lines.length > 0 && (
          <div style={{ padding: "0 20px" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ textAlign: "left", color: "var(--text3)", fontSize: 11, textTransform: "uppercase", letterSpacing: ".6px" }}>
                  <th style={{ padding: "8px 6px" }}>Statement line</th>
                  <th style={{ padding: "8px 6px", textAlign: "right" }}>Amount</th>
                  <th style={{ padding: "8px 6px" }}>Proposed code</th>
                  <th style={{ padding: "8px 6px", width: 140 }}>Confidence</th>
                </tr>
              </thead>
              <tbody>
                {data.lines.map((ln) => (
                  <React.Fragment key={ln.txn_id}>
                    <tr
                      onClick={() => setOpen(open === ln.txn_id ? null : ln.txn_id)}
                      style={{ cursor: "pointer", borderTop: "1px solid var(--border)" }}
                    >
                      <td style={{ padding: "10px 6px" }}>
                        <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 12 }}>{ln.description}</div>
                        <div style={{ fontSize: 11, color: "var(--text3)" }}>{ln.bank}</div>
                      </td>
                      <td style={{ padding: "10px 6px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                        {fmtAmount(ln.amount)}
                      </td>
                      <td style={{ padding: "10px 6px" }}>
                        <strong>{ln.gl_code}</strong>{" "}
                        <span style={{ color: "var(--text2)" }}>{ln.gl_label}</span>
                        {ln.status === "needs_review" && (
                          <span style={{ marginLeft: 8, fontSize: 10, color: "var(--red)", textTransform: "uppercase", letterSpacing: ".6px" }}>
                            needs review
                          </span>
                        )}
                      </td>
                      <td style={{ padding: "10px 6px" }}>
                        <ConfidenceBar value={ln.confidence} />
                      </td>
                    </tr>
                    {open === ln.txn_id && (
                      <tr>
                        <td colSpan={4} style={{ padding: "0 20px 12px", background: "var(--surface2)" }}>
                          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--gold-dark)", marginBottom: 6, marginTop: 8 }}>
                            Why this code?
                          </div>
                          <WhyCards
                            why={ln.explanation}
                            confidence={ln.confidence}
                            modelP={ln.confidence}
                          />
                          {ln.alternatives.length > 0 && (
                            <div style={{ marginTop: 8, fontSize: 11, color: "var(--text2)" }}>
                              Also considered:{" "}
                              {ln.alternatives.map((a, i) => (
                                <span key={a.gl_code}>
                                  {i > 0 && " · "}
                                  <strong>{a.gl_code}</strong> {a.gl_label} {(a.p * 100).toFixed(0)}%
                                </span>
                              ))}
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <AitoPanel config={PANEL} />
      </main>
    </>
  );
}
