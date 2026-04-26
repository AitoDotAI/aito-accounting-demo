"use client";

import { useEffect, useState } from "react";
import { useCustomer } from "@/lib/customer-context";
import { apiFetch, fmtAmount } from "@/lib/api";
import LiftHint from "@/components/prediction/LiftHint";
import type { InvoicePrediction } from "@/lib/types";

interface VendorHistoryRow {
  invoice_id: string;
  invoice_date?: string;
  amount: number;
  category?: string;
  gl_code: string;
  approver: string;
  vat_pct?: number;
}

type Tab = "prediction" | "history" | "routing";

export default function InvoiceDetail({ inv }: { inv: InvoicePrediction }) {
  const { customerId } = useCustomer();
  const [tab, setTab] = useState<Tab>("prediction");
  const [history, setHistory] = useState<VendorHistoryRow[] | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Reset tab + history when the selected invoice changes
  useEffect(() => {
    setTab("prediction");
    setHistory(null);
  }, [inv.invoice_id]);

  // Load vendor history lazily when the History tab is opened
  useEffect(() => {
    if (tab !== "history" || history !== null) return;
    setHistoryLoading(true);
    apiFetch<{ invoices: VendorHistoryRow[] }>(
      `/api/invoices/by_vendor?customer_id=${encodeURIComponent(customerId)}&vendor=${encodeURIComponent(inv.vendor)}&limit=12`,
    )
      .then((r) => setHistory(r.invoices))
      .catch(() => setHistory([]))
      .finally(() => setHistoryLoading(false));
  }, [tab, history, customerId, inv.vendor]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Tabs */}
      <div style={{ display: "flex", gap: 0, borderBottom: "1px solid var(--border2)", flexShrink: 0 }}>
        {(
          [
            { id: "prediction", label: "Prediction" },
            { id: "history", label: `Vendor history` },
            { id: "routing", label: "Routing trail" },
          ] as { id: Tab; label: string }[]
        ).map((t) => {
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              style={{
                padding: "10px 18px",
                fontSize: 12,
                fontWeight: 600,
                background: "transparent",
                border: "none",
                borderBottom: active ? "2px solid var(--gold-dark)" : "2px solid transparent",
                color: active ? "var(--gold-dark)" : "var(--text3)",
                cursor: "pointer",
                fontFamily: "inherit",
                textTransform: "uppercase",
                letterSpacing: ".6px",
              }}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      <div style={{ flex: 1, minHeight: 0, overflow: "auto", padding: 16 }}>
        {tab === "prediction" && <PredictionTab inv={inv} />}
        {tab === "history" && (
          <HistoryTab inv={inv} history={history} loading={historyLoading} />
        )}
        {tab === "routing" && <RoutingTab inv={inv} />}
      </div>
    </div>
  );
}

// ── Prediction tab ──────────────────────────────────────────────

function PredictionTab({ inv }: { inv: InvoicePrediction }) {
  const glAlts = inv.gl_alternatives ?? [];
  const apprAlts = inv.approver_alternatives ?? [];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
      <AlternativesCard title="GL code — top alternatives" predicted={inv.gl_code} alts={glAlts} format={(v) => v} />
      <AlternativesCard title="Approver — top alternatives" predicted={inv.approver} alts={apprAlts} format={(v) => v} />
    </div>
  );
}

interface Alternative {
  value: string;
  display: string;
  confidence: number;
  why?: { field: string; value: string; lift: number }[];
}

function AlternativesCard({
  title,
  predicted,
  alts,
  format,
}: {
  title: string;
  predicted: string | null;
  alts: Alternative[];
  format: (v: string) => string;
}) {
  if (alts.length === 0) {
    return (
      <div style={{ padding: 12, fontSize: 12, color: "var(--text3)" }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", marginBottom: 8 }}>{title}</div>
        No alternatives available — rule-based prediction or no Aito call.
      </div>
    );
  }
  const max = Math.max(...alts.map((a) => a.confidence));
  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", marginBottom: 10 }}>{title}</div>
      {alts.slice(0, 3).map((a) => {
        const isTop = a.value === predicted;
        const pct = max > 0 ? (a.confidence / max) * 100 : 0;
        return (
          <div key={a.value} style={{ marginBottom: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 12, marginBottom: 3 }}>
              <span style={{ fontWeight: isTop ? 700 : 500, color: isTop ? "var(--gold-dark)" : "var(--text2)" }}>
                {format(a.display || a.value)}
              </span>
              <span className="mono" style={{ fontSize: 11, color: "var(--text3)" }}>{(a.confidence * 100).toFixed(1)}%</span>
            </div>
            <div style={{ height: 4, background: "var(--surface2)", borderRadius: 2, overflow: "hidden" }}>
              <div style={{ height: "100%", width: `${pct}%`, background: isTop ? "var(--gold-dark)" : "var(--gold-light)" }} />
            </div>
            {isTop && a.why && a.why.length > 0 && (
              <div style={{ marginTop: 8, paddingLeft: 10, borderLeft: "2px solid var(--border2)" }}>
                <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", marginBottom: 4 }}>$why factors</div>
                {a.why.slice(0, 4).map((w, i) => (
                  <div key={i} style={{ fontSize: 11, color: "var(--text2)", padding: "2px 0", display: "flex", justifyContent: "space-between", gap: 8 }}>
                    <span>
                      <code style={{ fontFamily: "'IBM Plex Mono', monospace", color: "var(--text3)" }}>{w.field}</code>
                      {" = "}
                      <strong>{w.value}</strong>
                    </span>
                    <LiftHint value={w.lift} prefix="" />
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── History tab ─────────────────────────────────────────────────

function HistoryTab({ inv, history, loading }: { inv: InvoicePrediction; history: VendorHistoryRow[] | null; loading: boolean }) {
  if (loading) return <div style={{ fontSize: 12, color: "var(--text3)" }}>Loading vendor history…</div>;
  if (!history || history.length === 0) return <div style={{ fontSize: 12, color: "var(--text3)" }}>No prior invoices for this vendor.</div>;

  // Aggregate GL distribution
  const glCounts: Record<string, number> = {};
  for (const r of history) glCounts[r.gl_code] = (glCounts[r.gl_code] || 0) + 1;
  const glRanked = Object.entries(glCounts).sort((a, b) => b[1] - a[1]);
  const total = history.length;

  return (
    <div>
      <div style={{ fontSize: 12, color: "var(--text2)", marginBottom: 8 }}>
        Last <strong>{total}</strong> invoices from <strong>{inv.vendor}</strong>. The pattern below is
        the historical signal Aito's <code>_predict</code> conditions on.
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        {glRanked.map(([gl, n]) => (
          <span key={gl} style={{
            fontSize: 11,
            padding: "3px 10px",
            background: gl === inv.gl_code ? "var(--gold-light)" : "var(--surface2)",
            border: `1px solid ${gl === inv.gl_code ? "#d8bc70" : "var(--border2)"}`,
            color: gl === inv.gl_code ? "var(--gold-dark)" : "var(--text2)",
            borderRadius: 3,
            fontWeight: 600,
          }}>
            GL {gl}: {n}/{total}
          </span>
        ))}
      </div>

      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", fontWeight: 600 }}>
            <th style={{ textAlign: "left", padding: "6px 8px", borderBottom: "1px solid var(--border2)" }}>Invoice</th>
            <th style={{ textAlign: "left", padding: "6px 8px", borderBottom: "1px solid var(--border2)" }}>Date</th>
            <th style={{ textAlign: "right", padding: "6px 8px", borderBottom: "1px solid var(--border2)" }}>Amount</th>
            <th style={{ textAlign: "left", padding: "6px 8px", borderBottom: "1px solid var(--border2)" }}>Category</th>
            <th style={{ textAlign: "left", padding: "6px 8px", borderBottom: "1px solid var(--border2)" }}>GL</th>
            <th style={{ textAlign: "left", padding: "6px 8px", borderBottom: "1px solid var(--border2)" }}>Approver</th>
          </tr>
        </thead>
        <tbody>
          {history.map((r) => {
            const isThis = r.invoice_id === inv.invoice_id;
            return (
              <tr key={r.invoice_id} style={{
                background: isThis ? "var(--gold-light)" : undefined,
                borderBottom: "1px solid var(--border2)",
              }}>
                <td className="mono" style={{ padding: "6px 8px", color: "var(--gold-dark)" }}>{r.invoice_id}</td>
                <td className="mono" style={{ padding: "6px 8px", color: "var(--text3)", fontSize: 11 }}>{r.invoice_date ?? "—"}</td>
                <td className="mono" style={{ padding: "6px 8px", textAlign: "right" }}>{fmtAmount(r.amount)}</td>
                <td style={{ padding: "6px 8px" }}>{r.category ?? "—"}</td>
                <td className="mono" style={{ padding: "6px 8px", fontWeight: 600 }}>{r.gl_code}</td>
                <td style={{ padding: "6px 8px", color: "var(--text2)" }}>{r.approver}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Routing tab ─────────────────────────────────────────────────

function RoutingTab({ inv }: { inv: InvoicePrediction }) {
  // Synthetic but plausible audit trail derived from invoice fields
  const date = inv.invoice_date || "";
  const events = [
    { ts: date, label: "Received via vendor portal", actor: "system" },
    { ts: date, label: "Initial OCR + field extraction", actor: "system" },
    {
      ts: date,
      label: inv.source === "rule"
        ? `Routed by mined rule → GL ${inv.gl_code}, approver ${inv.approver}`
        : inv.source === "aito"
        ? `Routed by Aito _predict → GL ${inv.gl_code} (p=${inv.gl_confidence.toFixed(2)})`
        : "Sent to human review queue (low confidence)",
      actor: inv.source,
    },
    {
      ts: "—",
      label: inv.confidence >= 0.85
        ? "Auto-approved — touchless"
        : inv.confidence >= 0.5
        ? `Pending approver: ${inv.approver}`
        : "Pending review by AP team",
      actor: inv.confidence >= 0.85 ? "system" : "pending",
    },
  ];

  return (
    <div>
      <div style={{ fontSize: 12, color: "var(--text2)", marginBottom: 12 }}>
        Synthesised from the invoice's <code>routed</code>, <code>routed_by</code>, and confidence
        fields. A real deployment populates this from the prediction_log audit trail.
      </div>

      <div style={{ position: "relative", paddingLeft: 24 }}>
        {events.map((e, i) => {
          const isLast = i === events.length - 1;
          const dotColor =
            e.actor === "rule" ? "var(--blue)" :
            e.actor === "aito" ? "var(--gold-dark)" :
            e.actor === "review" ? "var(--amber)" :
            e.actor === "pending" ? "var(--amber)" :
            "var(--text3)";
          return (
            <div key={i} style={{ position: "relative", paddingBottom: isLast ? 0 : 16 }}>
              {!isLast && <div style={{ position: "absolute", left: -16, top: 12, bottom: 0, width: 1, background: "var(--border2)" }} />}
              <div style={{ position: "absolute", left: -20, top: 4, width: 9, height: 9, borderRadius: "50%", background: dotColor, border: "2px solid var(--surface)" }} />
              <div style={{ fontSize: 12.5, color: "var(--text)", lineHeight: 1.5 }}>{e.label}</div>
              <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 2, fontFamily: "'IBM Plex Mono', monospace" }}>
                {e.ts}{e.actor !== "pending" && ` · ${e.actor}`}
              </div>
            </div>
          );
        })}
      </div>

      <div style={{ marginTop: 20, padding: 12, background: "var(--surface2)", borderRadius: 4, fontSize: 11, color: "var(--text3)", lineHeight: 1.6 }}>
        <strong style={{ color: "var(--text2)" }}>Production note:</strong> a real ledger integration
        backfills this timeline from the prediction_log + overrides tables, plus webhook events from
        the ERP.
      </div>
    </div>
  );
}
