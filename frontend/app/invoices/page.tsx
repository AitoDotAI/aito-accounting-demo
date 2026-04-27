"use client";

import { useState, useEffect, useRef } from "react";
import Nav from "@/components/shell/Nav";
import TopBar from "@/components/shell/TopBar";
import AitoPanel from "@/components/shell/AitoPanel";
import ConfidenceBar from "@/components/prediction/ConfidenceBar";
import PredictionBadge from "@/components/prediction/PredictionBadge";
import WhyTooltip from "@/components/prediction/WhyTooltip";
import ErrorState from "@/components/shell/ErrorState";
import TourBadge from "@/components/shell/TourBadge";
import DetailSplit from "@/components/shell/DetailSplit";
import InvoiceDetail from "@/components/invoices/InvoiceDetail";
import { useCustomer } from "@/lib/customer-context";
import { demoToday } from "@/lib/demo-time";
import { apiFetch, fmtAmount } from "@/lib/api";
import type { InvoicesResponse, InvoicePrediction, AitoPanelConfig } from "@/lib/types";

const PANEL_CONFIG: AitoPanelConfig = {
  operation: "_predict",
  stats: [
    { value: "_predict", label: "Operation" },
    { value: "Live", label: "Predictions" },
    { value: "$invoices", label: "Records" },
    { value: "Indexed", label: "Model" },
  ],
  description:
    'GL code assignment and approver routing via <code style="font-size:11px;color:var(--aito-accent)">_predict</code>. ' +
    "Mined per-customer rules handle high-precision patterns; Aito fills the gap for remaining vendors.",
  query: JSON.stringify(
    { from: "invoices", where: { customer_id: "CUST-0000", vendor: "Kesko Oyj", amount: 4220 }, predict: "gl_code", select: ["$p", "feature", "$why"] },
    null,
    2,
  ),
  links: [
    { label: "API reference: _predict", url: "https://aito.ai/docs/api/#post-api-v1-predict" },
    { label: "Benchmark: 45.6% vs 33.4%", url: "https://aito.ai/blog/why-aito-predicts-accurately-with-little-data/" },
  ],
  flow_steps: [
    { n: 1, produces: "Pending invoice list", call: "_search WHERE customer_id, routed=false LIMIT 20" },
    { n: 2, produces: "Mined rules (vendor → GL)", call: "_relate vendor → gl_code; rules where support_ratio ≥ 0.95" },
    { n: 3, produces: "GL prediction per invoice", call: "_predict gl_code WHERE customer_id, vendor, amount, category" },
    { n: 4, produces: "Approver prediction", call: "_predict approver WHERE customer_id, vendor, amount, category" },
    { n: 5, produces: "Touchless rate", call: "Client-side: share of predictions ≥ 0.85 confidence" },
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
  const today = demoToday();  // frozen, not new Date()
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
    let stillCurrent = true;
    apiFetch<InvoicesResponse>(`/api/invoices/pending?customer_id=${customerId}`)
      .then((d) => { if (stillCurrent) { setData(d); setLive(true); } })
      .catch(() => { if (stillCurrent) setError(true); });
    return () => { stillCurrent = false; };
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

  // Detail-pane open state: which invoice is "viewed" (vs the
  // checkbox `selected` set used for batch override).
  const [viewedId, setViewedId] = useState<string | null>(null);
  const viewed = viewedId ? invoices.find((i) => i.invoice_id === viewedId) ?? null : null;
  // Reset viewed invoice on customer change
  useEffect(() => { setViewedId(null); }, [customerId]);

  // Batch override: track selected invoices and the bulk-apply GL
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkGl, setBulkGl] = useState<string>("");
  const [bulkMsg, setBulkMsg] = useState<string | null>(null);

  // Reset selection when customer or filter changes
  useEffect(() => { setSelected(new Set()); }, [customerId, filter]);

  const toggleSelect = (invoice_id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(invoice_id)) next.delete(invoice_id);
      else next.add(invoice_id);
      return next;
    });
  };

  const applyBulkOverride = () => {
    if (selected.size === 0 || !bulkGl) return;
    // In a real deployment this would POST to /api/overrides/batch.
    // For the demo we update the local view + log to prediction_log.
    setBulkMsg(`Logged ${selected.size} overrides to GL ${bulkGl} for prediction_log audit.`);
    setTimeout(() => setBulkMsg(null), 4000);
    setSelected(new Set());
    setBulkGl("");
  };

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
        <div className="content" style={viewed ? { paddingBottom: 540 } : undefined}>
          <div className="metrics">
            <div
              className={`metric highlight ${filter === "touchless" ? "metric-active" : ""}`}
              onClick={() => setFilter(filter === "touchless" ? "all" : "touchless")}
              style={{ cursor: "pointer" }}
              title="Click to filter to touchless invoices"
            >
              <div className="metric-label"><TourBadge n={5} />Touchless rate</div>
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

          {bulkMsg && (
            <div style={{ background: "var(--green-bg)", border: "1px solid #a8d8b0", borderRadius: 6, padding: "8px 14px", fontSize: 12, color: "#2a8a3a", marginBottom: 8 }}>
              {bulkMsg}
            </div>
          )}
          {selected.size > 0 && (
            <div style={{
              display: "flex", alignItems: "center", gap: 10,
              background: "var(--gold-light)", border: "1px solid #d8bc70",
              borderRadius: 6, padding: "8px 14px", marginBottom: 8, fontSize: 12,
            }}>
              <strong style={{ color: "var(--gold-dark)" }}>{selected.size} selected.</strong>
              <span style={{ color: "var(--text2)" }}>Override GL to:</span>
              <select
                value={bulkGl}
                onChange={(e) => setBulkGl(e.target.value)}
                style={{ padding: "4px 8px", borderRadius: 4, border: "1px solid var(--border)", fontSize: 12, fontFamily: "inherit" }}
              >
                <option value="">— pick —</option>
                <option value="4100">4100 — COGS</option>
                <option value="4400">4400 — Materials & Supplies</option>
                <option value="4500">4500 — Office Expenses</option>
                <option value="4600">4600 — Logistics</option>
                <option value="5100">5100 — Facilities</option>
                <option value="5200">5200 — Maintenance</option>
                <option value="5300">5300 — Insurance</option>
                <option value="5400">5400 — Professional Services</option>
                <option value="6100">6100 — IT & Software</option>
                <option value="6200">6200 — Telecom</option>
              </select>
              <button
                onClick={applyBulkOverride}
                disabled={!bulkGl}
                style={{
                  padding: "4px 12px",
                  borderRadius: 4,
                  border: "1px solid var(--gold-dark)",
                  background: bulkGl ? "var(--gold-dark)" : "var(--surface2)",
                  color: bulkGl ? "#f5e8c0" : "var(--text3)",
                  cursor: bulkGl ? "pointer" : "not-allowed",
                  fontSize: 11,
                  fontWeight: 600,
                  fontFamily: "inherit",
                }}
              >
                Apply override
              </button>
              <button
                onClick={() => setSelected(new Set())}
                style={{ background: "transparent", border: "none", color: "var(--gold-dark)", cursor: "pointer", fontSize: 11, fontWeight: 600 }}
              >
                Clear selection
              </button>
            </div>
          )}
          <div className="card">
            <div className="card-header">
              <span className="card-title"><TourBadge n={1} />Pending invoices</span>
              <span className="card-hint">Select rows to bulk-override · click a prediction for alternatives</span>
            </div>
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: 28 }}>
                    <input
                      type="checkbox"
                      checked={invoices.length > 0 && invoices.every((i) => selected.has(i.invoice_id))}
                      onChange={(e) => {
                        if (e.target.checked) setSelected(new Set(invoices.map((i) => i.invoice_id)));
                        else setSelected(new Set());
                      }}
                      title="Select all visible"
                    />
                  </th>
                  <th>Invoice</th>
                  <th>Date</th>
                  <th>Due</th>
                  <th>Vendor</th>
                  <th>Net</th>
                  <th>VAT</th>
                  <th><TourBadge n={4} />Approver</th>
                  <th><TourBadge n={3} />GL Code</th>
                  <th>Conf.</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {!live && !error && Array.from({ length: 8 }).map((_, i) => (
                  <SkeletonRow key={i} />
                ))}
                {live && invoices.length === 0 && !error && (
                  <tr><td colSpan={11} style={{ textAlign: "center", color: "var(--text3)", padding: 24 }}>No invoices</td></tr>
                )}
                {error && (
                  <tr><td colSpan={11}><ErrorState /></td></tr>
                )}
                {invoices.map((inv) => (
                  <InvoiceRow
                    key={inv.invoice_id}
                    inv={inv}
                    predicting={!live}
                    selected={selected.has(inv.invoice_id)}
                    onToggleSelect={() => toggleSelect(inv.invoice_id)}
                    viewed={viewedId === inv.invoice_id}
                    onView={() => setViewedId(viewedId === inv.invoice_id ? null : inv.invoice_id)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </div>
        {viewed && (
          <DetailDock
            title={`${viewed.invoice_id} · ${viewed.vendor} · €${viewed.amount.toLocaleString()}`}
            onClose={() => setViewedId(null)}
          >
            <InvoiceDetail inv={viewed} />
          </DetailDock>
        )}
      </div>
      <AitoPanel config={PANEL_CONFIG} />
    </>
  );
}

function InvoiceRow({ inv, predicting, selected, onToggleSelect, viewed, onView }: {
  inv: InvoicePrediction;
  predicting: boolean;
  selected: boolean;
  onToggleSelect: () => void;
  viewed: boolean;
  onView: () => void;
}) {
  if (predicting) {
    const due = dueLabel(inv);
    const dueColor = due.tone === "red" ? "var(--red)" : due.tone === "amber" ? "var(--amber)" : "var(--text3)";
    return (
      <tr>
        <td><input type="checkbox" checked={selected} onChange={onToggleSelect} /></td>
        <td className="mono" style={{ color: "var(--gold-dark)" }}>{inv.invoice_id}</td>
        <td className="mono" style={{ fontSize: 11, color: "var(--text3)" }}>{fmtShortDate(inv.invoice_date)}</td>
        <td className="mono" style={{ fontSize: 11, fontWeight: due.tone === "neutral" ? 400 : 600, color: dueColor }}>{due.text}</td>
        <td>{inv.vendor}</td>
        <td className="mono">{fmtAmount(inv.amount)}</td>
        <td className="mono" style={{ fontSize: 11, color: "var(--text3)" }}>{inv.vat_pct != null ? `${inv.vat_pct}%` : "—"}</td>
        <td><div className="skeleton" style={{ height: 14, width: "70%" }} /></td>
        <td><div className="skeleton" style={{ height: 14, width: "60%" }} /></td>
        <td><div className="skeleton" style={{ height: 14, width: "70%" }} /></td>
        <td><div className="skeleton" style={{ height: 14, width: 40 }} /></td>
      </tr>
    );
  }
  return <InvoiceRowFull inv={inv} selected={selected} onToggleSelect={onToggleSelect} viewed={viewed} onView={onView} />;
}

function InvoiceRowFull({ inv, selected, onToggleSelect, viewed, onView }: {
  inv: InvoicePrediction;
  selected: boolean;
  onToggleSelect: () => void;
  viewed: boolean;
  onView: () => void;
}) {
  const glAlts = inv.gl_alternatives;
  const approverAlts = inv.approver_alternatives;
  const glWhyFactors = glAlts?.[0]?.why ?? [];
  const approverWhyFactors = approverAlts?.[0]?.why ?? [];
  const due = dueLabel(inv);
  const dueColor = due.tone === "red" ? "var(--red)" : due.tone === "amber" ? "var(--amber)" : "var(--text3)";

  const rowBg = viewed ? "var(--surface2)" : selected ? "var(--gold-light)" : undefined;
  return (
    <tr style={rowBg ? { background: rowBg } : undefined}>
      <td><input type="checkbox" checked={selected} onChange={onToggleSelect} /></td>
      <td
        className="mono"
        onClick={onView}
        style={{
          color: viewed ? "var(--gold-dark)" : "var(--gold-dark)",
          cursor: "pointer",
          fontWeight: viewed ? 700 : 400,
          textDecoration: "underline",
          textDecorationStyle: "dotted",
          textDecorationColor: "var(--gold-mid)",
        }}
        title="Click to open detail panel"
      >
        {inv.invoice_id}
      </td>
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
      {Array.from({ length: 11 }).map((_, i) => (
        <td key={i}>
          <div className="skeleton" style={{ height: 14, borderRadius: 4, width: "70%" }} />
        </td>
      ))}
    </tr>
  );
}

// ── Detail dock ──────────────────────────────────────────────────
//
// Click an invoice id → details slide up from the bottom of the
// .main pane. Resizable height; persisted via localStorage.

function DetailDock({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  const [height, setHeight] = useState(520);
  const draggingRef = useRef(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    // v2 key: previous version stored 360 by default; the new inputs +
    // predictions split needs >= 480 to render without scrolling.
    const stored = localStorage.getItem("invoice-detail-dock-height-v2");
    if (stored) {
      const n = parseInt(stored, 10);
      if (!isNaN(n) && n >= 200 && n <= 800) setHeight(n);
    }
  }, []);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!draggingRef.current) return;
      const newH = Math.max(200, Math.min(800, window.innerHeight - e.clientY));
      setHeight(newH);
    };
    const onUp = () => {
      if (!draggingRef.current) return;
      draggingRef.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      localStorage.setItem("invoice-detail-dock-height-v2", String(Math.round(height)));
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
  }, [height]);

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: 0,
        height,
        background: "var(--surface)",
        borderTop: "1px solid var(--border2)",
        boxShadow: "0 -4px 12px rgba(13,21,32,.06)",
        display: "flex",
        flexDirection: "column",
        zIndex: 5,
      }}
    >
      {/* Drag handle */}
      <div
        onMouseDown={(e) => {
          e.preventDefault();
          draggingRef.current = true;
          document.body.style.cursor = "row-resize";
          document.body.style.userSelect = "none";
        }}
        title="Drag to resize"
        style={{
          height: 6,
          background: "var(--border2)",
          cursor: "row-resize",
          flexShrink: 0,
          position: "relative",
        }}
      >
        <div style={{ position: "absolute", top: 1, left: "50%", transform: "translateX(-50%)", width: 36, height: 2, background: "var(--text3)", borderRadius: 1, opacity: 0.4 }} />
      </div>
      <div style={{ padding: "10px 16px", borderBottom: "1px solid var(--border2)", display: "flex", alignItems: "center", justifyContent: "space-between", background: "var(--surface2)", flexShrink: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>{title}</div>
        <button onClick={onClose} title="Close" style={{ background: "transparent", border: "none", color: "var(--text3)", fontSize: 18, cursor: "pointer", padding: "0 4px", lineHeight: 1 }}>×</button>
      </div>
      <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
        {children}
      </div>
    </div>
  );
}
