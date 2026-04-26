"use client";

import { useState, useEffect } from "react";
import Nav from "@/components/shell/Nav";
import TopBar from "@/components/shell/TopBar";
import AitoPanel from "@/components/shell/AitoPanel";
import ConfidenceBar from "@/components/prediction/ConfidenceBar";
import PredictionBadge from "@/components/prediction/PredictionBadge";
import WhyTooltip from "@/components/prediction/WhyTooltip";
import ErrorState from "@/components/shell/ErrorState";
import { useCustomer } from "@/lib/customer-context";
import { apiFetch, fmtAmount } from "@/lib/api";
import type { InvoicesResponse, InvoicePrediction, AitoPanelConfig } from "@/lib/types";

const PANEL_CONFIG: AitoPanelConfig = {
  operation: "_predict",
  stats: [
    { value: "_predict", label: "Operation" },
    { value: "Live", label: "Predictions" },
    { value: "$invoices", label: "Records" },
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

function touchlessPct(invoices: InvoicePrediction[]): number {
  if (invoices.length === 0) return 0;
  const touchless = invoices.filter((inv) => inv.confidence >= 0.85).length;
  return Math.round((touchless / invoices.length) * 100);
}

function dueDate(inv: InvoicePrediction): Date | null {
  if (!inv.invoice_date) return null;
  const d = new Date(inv.invoice_date);
  if (isNaN(d.getTime())) return null;
  d.setDate(d.getDate() + (inv.due_days ?? 30));
  return d;
}

function fmtShortDate(d: string | null | undefined): string {
  if (!d) return "—";
  const date = new Date(d);
  if (isNaN(date.getTime())) return d;
  return date.toLocaleDateString("fi-FI", { day: "2-digit", month: "2-digit", year: "2-digit" });
}

function dueLabel(inv: InvoicePrediction): { text: string; tone: "red" | "amber" | "neutral" } {
  const due = dueDate(inv);
  if (!due) return { text: "—", tone: "neutral" };
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const days = Math.round((due.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
  if (days < 0) return { text: `${-days}d overdue`, tone: "red" };
  if (days === 0) return { text: "Due today", tone: "red" };
  if (days <= 7) return { text: `Due in ${days}d`, tone: "amber" };
  return { text: fmtShortDate(due.toISOString()), tone: "neutral" };
}

export default function InvoicesPage() {
  const { customerId } = useCustomer();
  const [data, setData] = useState<InvoicesResponse | null>(null);
  const [live, setLive] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    setData(null); setLive(false); setError(false);
    apiFetch<InvoicesResponse>(`/api/invoices/pending?customer_id=${customerId}`)
      .then((d) => { setData(d); setLive(true); })
      .catch(() => setError(true));
  }, [customerId]);

  const metrics = data?.metrics;
  type Filter = "all" | "touchless" | "review" | "rule" | "aito";
  const [filter, setFilter] = useState<Filter>("all");
  const allInvoices = (data?.invoices ?? []).slice().sort((a, b) => {
    const da = dueDate(a)?.getTime() ?? Infinity;
    const db = dueDate(b)?.getTime() ?? Infinity;
    return da - db;
  });
  const invoices = allInvoices.filter((inv) => {
    switch (filter) {
      case "touchless": return inv.confidence >= 0.85;
      case "review":    return inv.source === "review" || inv.confidence < 0.85;
      case "rule":      return inv.source === "rule";
      case "aito":      return inv.source === "aito";
      default: return true;
    }
  });

  return (
    <>
      <Nav />
      <div className="main">
        <TopBar
          breadcrumb="Payables"
          title="Invoice Processing"
          subtitle={metrics ? `${metrics.total} pending \u00B7 ${metrics.review_count} require review` : "Loading..."}
          live={live}
        />
        <div className="content">
          <div className="metrics">
            <div
              className={`metric highlight ${filter === "touchless" ? "metric-active" : ""}`}
              onClick={() => setFilter(filter === "touchless" ? "all" : "touchless")}
              style={{ cursor: "pointer" }}
              title="Click to filter to touchless invoices"
            >
              <div className="metric-label">Touchless rate</div>
              <div className="metric-value">{metrics ? `${touchlessPct(allInvoices)}%` : "--"}</div>
              <div className="metric-sub metric-neutral">
                Predicted at &ge; 0.85 confidence
              </div>
            </div>
            <div className="metric">
              <div className="metric-label">Avg confidence</div>
              <div className="metric-value">{metrics?.avg_confidence.toFixed(2) ?? "--"}</div>
              <div className="metric-sub metric-neutral">
                {metrics ? `${metrics.rule_count} rules · ${metrics.aito_count} Aito` : ""}
              </div>
            </div>
            <div className="metric">
              <div className="metric-label">Pending</div>
              <div className="metric-value">{metrics?.total ?? "--"}</div>
            </div>
            <div
              className={`metric ${filter === "review" ? "metric-active" : ""}`}
              onClick={() => setFilter(filter === "review" ? "all" : "review")}
              style={{ cursor: "pointer" }}
              title="Click to filter to invoices needing review"
            >
              <div className="metric-label">Review needed</div>
              <div className="metric-value" style={{ color: metrics?.review_count ? "var(--amber)" : undefined }}>{metrics?.review_count ?? "--"}</div>
              <div className="metric-sub metric-neutral">
                {metrics?.review_count ? "Below confidence threshold" : "All above threshold"}
              </div>
            </div>
          </div>
          {filter !== "all" && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, padding: "6px 12px", background: "var(--gold-light)", border: "1px solid #d8bc70", borderRadius: 6, fontSize: 12 }}>
              <span style={{ color: "var(--gold-dark)", fontWeight: 600 }}>Filtered:</span>
              <span style={{ color: "var(--text2)" }}>
                {filter === "touchless" && `Showing ${invoices.length} touchless invoices (≥0.85 confidence)`}
                {filter === "review" && `Showing ${invoices.length} invoices needing review (<0.85 confidence)`}
                {filter === "rule" && `Showing ${invoices.length} rule-routed invoices`}
                {filter === "aito" && `Showing ${invoices.length} Aito-predicted invoices`}
              </span>
              <button
                onClick={() => setFilter("all")}
                style={{ marginLeft: "auto", background: "transparent", border: "none", color: "var(--gold-dark)", cursor: "pointer", fontSize: 12, fontWeight: 600 }}
              >
                Clear filter ×
              </button>
            </div>
          )}

          <div className="card">
            <div className="card-header">
              <span className="card-title">Pending invoices</span>
              <span className="card-hint">Click a prediction to see alternatives</span>
            </div>
            <table className="table">
              <thead>
                <tr>
                  <th>Invoice</th>
                  <th>Date</th>
                  <th>Due</th>
                  <th>Vendor</th>
                  <th>Net</th>
                  <th>VAT</th>
                  <th>Approver</th>
                  <th>GL Code</th>
                  <th>Conf.</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {!live && !error && Array.from({ length: 8 }).map((_, i) => (
                  <SkeletonRow key={i} />
                ))}
                {live && invoices.length === 0 && !error && (
                  <tr><td colSpan={10} style={{ textAlign: "center", color: "var(--text3)", padding: 24 }}>No invoices</td></tr>
                )}
                {error && (
                  <tr><td colSpan={10}><ErrorState /></td></tr>
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
  const due = dueLabel(inv);
  const dueColor = due.tone === "red" ? "var(--red)" : due.tone === "amber" ? "var(--amber)" : "var(--text3)";

  return (
    <tr>
      <td className="mono" style={{ color: "var(--gold-dark)", cursor: "pointer" }}>{inv.invoice_id}</td>
      <td className="mono" style={{ fontSize: 11, color: "var(--text3)" }}>{fmtShortDate(inv.invoice_date)}</td>
      <td className="mono" style={{ fontSize: 11, fontWeight: due.tone === "neutral" ? 400 : 600, color: dueColor }}>{due.text}</td>
      <td>{inv.vendor}</td>
      <td className="mono">{fmtAmount(inv.amount)}</td>
      <td className="mono" style={{ fontSize: 11, color: "var(--text3)" }}>{inv.vat_pct != null ? `${inv.vat_pct}%` : "—"}</td>
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

function SkeletonRow() {
  return (
    <tr>
      {Array.from({ length: 10 }).map((_, i) => (
        <td key={i}>
          <div className="skeleton" style={{ height: 14, borderRadius: 4, width: "70%" }} />
        </td>
      ))}
    </tr>
  );
}
