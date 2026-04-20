"use client";

import { useState, useEffect } from "react";
import Nav from "@/components/shell/Nav";
import TopBar from "@/components/shell/TopBar";
import AitoPanel from "@/components/shell/AitoPanel";
import ConfidenceBar from "@/components/prediction/ConfidenceBar";
import PredictionBadge from "@/components/prediction/PredictionBadge";
import WhyTooltip from "@/components/prediction/WhyTooltip";
import ErrorState from "@/components/shell/ErrorState";
import { apiFetch, fmtAmount } from "@/lib/api";
import type { InvoicesResponse, InvoicePrediction, AitoPanelConfig } from "@/lib/types";

const PANEL_CONFIG: AitoPanelConfig = {
  operation: "_predict",
  stats: [
    { value: "0.91", label: "Confidence" },
    { value: "27ms", label: "Response" },
    { value: "230", label: "Records" },
    { value: "Zero", label: "Training" },
  ],
  description:
    'GL code assignment and approver routing via <code style="font-size:11px;color:var(--aito-accent)">_predict</code>. ' +
    "Rules handle known patterns (Telia, Elisa). Aito fills the gap for remaining vendors.",
  query: JSON.stringify(
    { from: "invoices", where: { vendor: "Kesko Oyj", amount: 4220 }, predict: "gl_code", select: ["$p", "feature", "$why"] },
    null,
    2,
  ),
  links: [
    { label: "API reference: _predict", url: "https://aito.ai/docs/api/#post-api-v1-predict" },
    { label: "Benchmark: 45.6% vs 33.4%", url: "https://aito.ai/blog/why-aito-predicts-accurately-with-little-data/" },
  ],
};

function sourceBadge(source: string) {
  if (source === "rule") return <span className="badge badge-blue">Rule</span>;
  if (source === "aito") return <span className="badge badge-gold">Aito</span>;
  return <span className="badge badge-amber">No match</span>;
}

export default function InvoicesPage() {
  const [data, setData] = useState<InvoicesResponse | null>(null);
  const [live, setLive] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    apiFetch<InvoicesResponse>("/api/invoices/pending")
      .then((d) => { setData(d); setLive(true); })
      .catch(() => setError(true));
  }, []);

  const metrics = data?.metrics;
  const invoices = data?.invoices ?? [];

  return (
    <>
      <Nav />
      <div className="main">
        <TopBar
          breadcrumb="Payables"
          title="Invoice Processing"
          subtitle={metrics ? `${metrics.total} pending \u00B7 ${metrics.review_count} require review` : "Loading..."}
          live={live}
          actions={
            <>
              <button className="btn btn-outline">Export</button>
              <button className="btn btn-primary">+ New Invoice</button>
            </>
          }
        />
        <div className="content">
          <div className="metrics">
            <div className="metric highlight">
              <div className="metric-label">Automation Rate</div>
              <div className="metric-value">{metrics ? `${Math.round(metrics.automation_rate * 100)}%` : "--"}</div>
              <div className="metric-sub metric-up">
                {metrics ? `\u2191 ${Math.round(metrics.automation_rate * 100) - metrics.rule_count}pp from rules-only` : ""}
              </div>
            </div>
            <div className="metric">
              <div className="metric-label">Avg Confidence</div>
              <div className="metric-value">{metrics?.avg_confidence.toFixed(2) ?? "--"}</div>
            </div>
            <div className="metric">
              <div className="metric-label">Processed</div>
              <div className="metric-value">{metrics?.total ?? "--"}</div>
              <div className="metric-sub metric-neutral">
                {metrics ? `${metrics.rule_count} rules \u00B7 ${metrics.aito_count} Aito` : ""}
              </div>
            </div>
            <div className="metric">
              <div className="metric-label">Exceptions</div>
              <div className="metric-value">{metrics?.review_count ?? "--"}</div>
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <span className="card-title">Pending invoices</span>
              <span className="card-hint">Click a prediction to see alternatives</span>
            </div>
            <table className="table">
              <thead>
                <tr>
                  <th>Invoice</th>
                  <th>Vendor</th>
                  <th>Amount</th>
                  <th>AI Routing</th>
                  <th>GL Code</th>
                  <th>Confidence</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {invoices.length === 0 && !error && (
                  <tr><td colSpan={7} style={{ textAlign: "center", color: "var(--text3)", padding: 24 }}>
                    {live ? "No invoices" : "Loading..."}
                  </td></tr>
                )}
                {error && (
                  <tr><td colSpan={7}><ErrorState /></td></tr>
                )}
                {invoices.map((inv) => (
                  <InvoiceRow key={inv.invoice_id} inv={inv} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      <AitoPanel config={PANEL_CONFIG} />
    </>
  );
}

function InvoiceRow({ inv }: { inv: InvoicePrediction }) {
  const glAlts = inv.gl_alternatives;
  const approverAlts = inv.approver_alternatives;
  const glWhyFactors = glAlts?.[0]?.why ?? [];
  const approverWhyFactors = approverAlts?.[0]?.why ?? [];

  return (
    <tr>
      <td className="mono" style={{ color: "var(--gold-dark)", cursor: "pointer" }}>{inv.invoice_id}</td>
      <td>{inv.vendor}</td>
      <td className="mono">{fmtAmount(inv.amount)}</td>
      <td>
        {inv.approver ? (
          <div style={{ display: "flex", alignItems: "center", gap: 2 }}>
            <PredictionBadge
              value={inv.approver}
              confidence={inv.approver_confidence}
              alternatives={approverAlts}
            />
            <WhyTooltip label={inv.approver} factors={approverWhyFactors} />
          </div>
        ) : (
          <span className="badge badge-amber">Review needed</span>
        )}
      </td>
      <td>
        {inv.gl_code ? (
          <div style={{ display: "flex", alignItems: "center", gap: 2 }}>
            <PredictionBadge
              value={`${inv.gl_code} \u2013 ${inv.gl_label}`}
              confidence={inv.gl_confidence}
              alternatives={glAlts}
            />
            <WhyTooltip label={`GL ${inv.gl_code}`} factors={glWhyFactors} />
          </div>
        ) : (
          <span className="badge badge-amber">Review needed</span>
        )}
      </td>
      <td><ConfidenceBar value={inv.confidence} /></td>
      <td>{sourceBadge(inv.source)}</td>
    </tr>
  );
}
