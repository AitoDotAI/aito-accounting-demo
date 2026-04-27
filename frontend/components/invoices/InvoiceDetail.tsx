"use client";

import { useEffect, useState, useMemo } from "react";
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
//
// Two-column layout: left = inputs (vendor, amount, description, ...)
// = the data Aito conditions on. Right = predictions (GL, approver)
// with their top-3 alternatives and $why factors. Hovering a $why
// row highlights the source field on the left -- and tokens within
// the description that drove the match get a yellow background.

interface Alternative {
  value: string;
  display: string;
  confidence: number;
  why?: { field: string; value: string; lift: number; type?: string }[];
}

interface Highlight {
  field: string | null;
  value: string | null;
}

function PredictionTab({ inv }: { inv: InvoicePrediction }) {
  const glAlts = inv.gl_alternatives ?? [];
  const apprAlts = inv.approver_alternatives ?? [];
  const [hl, setHl] = useState<Highlight>({ field: null, value: null });

  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1.3fr)", gap: 20 }}>
      <InvoiceInputs inv={inv} hl={hl} />
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <AlternativesCard
          title="GL code — top alternatives"
          predicted={inv.gl_code}
          alts={glAlts}
          format={(v) => v}
          onHoverFactor={setHl}
        />
        <AlternativesCard
          title="Approver — top alternatives"
          predicted={inv.approver}
          alts={apprAlts}
          format={(v) => v}
          onHoverFactor={setHl}
        />
      </div>
    </div>
  );
}

function InvoiceInputs({ inv, hl }: { inv: InvoicePrediction; hl: Highlight }) {
  // Compact 2-column grid for the structured fields, then a full-
  // width description row at the bottom so long text wraps naturally.
  const grid: { field: string; label: string; value: React.ReactNode }[] = [
    { field: "vendor", label: "Vendor", value: inv.vendor },
    { field: "vendor_country", label: "Country", value: inv.vendor_country || "—" },
    { field: "category", label: "Category", value: inv.category || "—" },
    { field: "amount", label: "Amount", value: fmtAmount(inv.amount) },
    { field: "vat_pct", label: "VAT %", value: inv.vat_pct != null ? `${inv.vat_pct}%` : "—" },
    { field: "invoice_date", label: "Invoice date", value: inv.invoice_date || "—" },
    { field: "due_days", label: "Due terms", value: inv.due_days != null ? `${inv.due_days} days` : "—" },
  ];

  const cell = (r: { field: string; label: string; value: React.ReactNode }) => {
    const lit = hl.field === r.field;
    return (
      <div
        key={r.field}
        style={{
          fontSize: 12, padding: "6px 10px", borderRadius: 4,
          background: lit ? "var(--gold-light)" : "var(--surface2)",
          borderLeft: lit ? "3px solid var(--gold-dark)" : "3px solid transparent",
          transition: "background .12s, border-color .12s",
          minWidth: 0,
        }}
      >
        <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", marginBottom: 2 }}>
          {r.label}
        </div>
        <div style={{ color: "var(--text)", lineHeight: 1.4, overflow: "hidden", textOverflow: "ellipsis" }}>{r.value}</div>
      </div>
    );
  };

  const descLit = hl.field === "description";
  return (
    <div>
      <div style={{
        fontSize: 11, fontWeight: 600, color: "var(--text3)",
        textTransform: "uppercase", letterSpacing: ".6px", marginBottom: 10,
      }}>
        Invoice inputs · Aito conditions on these
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 6 }}>
        {grid.map(cell)}
      </div>
      <div style={{
        fontSize: 12, padding: "6px 10px", borderRadius: 4,
        background: descLit ? "var(--gold-light)" : "var(--surface2)",
        borderLeft: descLit ? "3px solid var(--gold-dark)" : "3px solid transparent",
        transition: "background .12s, border-color .12s",
      }}>
        <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", marginBottom: 2 }}>
          Description
        </div>
        <div style={{ color: "var(--text)", lineHeight: 1.5 }}>
          <DescriptionCell text={inv.description ?? ""} highlightedTokens={descLit ? hl.value : null} />
        </div>
      </div>
    </div>
  );
}

function DescriptionCell({ text, highlightedTokens }: { text: string; highlightedTokens: string | null }) {
  // Tokenize the description and highlight any token that appears in
  // the $why value the user is hovering. Aito's analyzer is roughly
  // word-level; doing the same on the client is good enough.
  const tokens = useMemo(() => {
    const set = new Set<string>();
    if (highlightedTokens) {
      for (const t of highlightedTokens.toLowerCase().split(/\W+/).filter((s) => s.length > 2)) {
        set.add(t);
      }
    }
    return set;
  }, [highlightedTokens]);

  if (!text) return <span style={{ color: "var(--text3)" }}>—</span>;
  if (tokens.size === 0) return <span>{text}</span>;

  const parts = text.split(/(\W+)/);
  return (
    <span>
      {parts.map((p, i) => {
        const hit = tokens.has(p.toLowerCase());
        return hit ? (
          <mark key={i} style={{ background: "#fff3a8", padding: "0 2px", borderRadius: 2 }}>
            {p}
          </mark>
        ) : (
          <span key={i}>{p}</span>
        );
      })}
    </span>
  );
}

function AlternativesCard({
  title,
  predicted,
  alts,
  format,
  onHoverFactor,
}: {
  title: string;
  predicted: string | null;
  alts: Alternative[];
  format: (v: string) => string;
  onHoverFactor: (h: Highlight) => void;
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
                <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", marginBottom: 4 }}>
                  $why factors · hover a row to highlight the source
                </div>
                {a.why.slice(0, 5).map((w, i) => (
                  <div
                    key={i}
                    onMouseEnter={() => onHoverFactor({ field: w.field, value: w.value })}
                    onMouseLeave={() => onHoverFactor({ field: null, value: null })}
                    style={{
                      fontSize: 11, color: "var(--text2)", padding: "3px 4px",
                      display: "flex", justifyContent: "space-between", gap: 8,
                      borderRadius: 3, cursor: "default",
                    }}
                    onMouseOver={(e) => (e.currentTarget.style.background = "var(--surface2)")}
                    onMouseOut={(e) => (e.currentTarget.style.background = "transparent")}
                  >
                    <span>
                      <code style={{ fontFamily: "'IBM Plex Mono', monospace", color: "var(--text3)" }}>
                        {w.type === "base" ? "base P" : w.field}
                      </code>
                      {w.type === "base" ? ` (${w.value})` : (
                        <>
                          {" = "}
                          <strong>{w.value}</strong>
                        </>
                      )}
                    </span>
                    {w.type === "base" ? (
                      <span style={{ fontSize: 10, fontWeight: 600, color: "var(--text3)" }}>
                        {(w.lift * 100).toFixed(1)}%
                      </span>
                    ) : (
                      <LiftHint value={w.lift} prefix="" />
                    )}
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
