"use client";

import LiftHint from "./LiftHint";
import type { WhyFactor } from "@/lib/types";

// ── $why factor cards ─────────────────────────────────────────────
//
// Mirrors aito-demo's InvoicingPage explanation layout:
// - "Base probability" card with the historical rate of the target
// - "Pattern match" cards showing "When <field> contains <highlighted-tokens>
//   and <field2> = <value>" with the lift multiplier per pattern
// - Calculation summary: 46% × 2.0 × ... = 99%
//
// Reused by:
// - InvoiceDetail's prediction tab (with onHoverFactor wired to the
//   left-side input panel for cross-highlight)
// - WhyTooltip popup (no onHoverFactor — popups don't have a sibling
//   panel to highlight)

export interface HoverHighlight {
  field: string | null;
  value: string | null;
}

export default function WhyCards({
  why,
  confidence,
  onHoverFactor,
}: {
  why: WhyFactor[];
  confidence: number;
  onHoverFactor?: (h: HoverHighlight) => void;
}) {
  const base = why.find((f) => f.type === "base");
  const patterns = why.filter((f) => f.type === "pattern");
  const legacy = why.filter((f) => !f.type && f.field);  // old precomputed JSON

  const baseP = base?.base_p ?? 0;
  const lifts = patterns.map((p) => p.lift ?? 1);
  const hover = onHoverFactor ?? (() => {});

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {base && (
        <div style={{
          background: "var(--surface2)", borderRadius: 4,
          padding: "8px 10px",
          display: "flex", justifyContent: "space-between", gap: 8,
        }}>
          <div>
            <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px" }}>
              Base probability
            </div>
            <div style={{ fontSize: 11, color: "var(--text2)" }}>
              Historical rate for <strong>{base.target_value || "this value"}</strong>
            </div>
          </div>
          <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text)" }}>
            {(baseP * 100).toFixed(0)}%
          </div>
        </div>
      )}

      {patterns.map((f, i) => {
        const props = f.propositions ?? [];
        const firstField = props[0]?.field ?? null;
        const firstValue = props[0]?.highlight ? props[0].value : (props[0]?.value ?? null);
        return (
          <div
            key={i}
            onMouseEnter={() => hover({ field: firstField, value: firstValue })}
            onMouseLeave={() => hover({ field: null, value: null })}
            style={{
              background: "var(--gold-light)",
              borderLeft: "3px solid var(--gold-dark)",
              borderRadius: 4,
              padding: "8px 10px",
              display: "flex", justifyContent: "space-between", gap: 12,
              cursor: "default",
            }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 10, color: "var(--gold-dark)", textTransform: "uppercase", letterSpacing: ".6px", fontWeight: 600 }}>
                Pattern match
              </div>
              <div style={{ fontSize: 11, color: "var(--text2)", lineHeight: 1.55 }}>
                When{" "}
                {props.map((p, pi) => {
                  const sep = pi === 0 ? "" : pi === props.length - 1 ? " and " : ", ";
                  const fieldLabel = p.field.replace(/^invoice_id\./, "");
                  const valueNode = p.highlight ? (
                    <span dangerouslySetInnerHTML={{ __html: p.highlight }} />
                  ) : (
                    <strong>{p.value}</strong>
                  );
                  return (
                    <span key={pi}>
                      {sep}
                      <code style={{ fontFamily: "'IBM Plex Mono', monospace", color: "var(--text3)" }}>{fieldLabel}</code>
                      {p.highlight ? " contains " : " = "}
                      {valueNode}
                    </span>
                  );
                })}
              </div>
            </div>
            <LiftHint value={f.lift ?? 1} prefix="× " />
          </div>
        );
      })}

      {/* Legacy flat factors (from old precomputed JSON) */}
      {legacy.map((f, i) => (
        <div
          key={`legacy-${i}`}
          onMouseEnter={() => hover({ field: f.field ?? null, value: f.value ?? null })}
          onMouseLeave={() => hover({ field: null, value: null })}
          style={{
            fontSize: 11, color: "var(--text2)", padding: "3px 4px",
            display: "flex", justifyContent: "space-between", gap: 8,
          }}
        >
          <span>
            <code style={{ fontFamily: "'IBM Plex Mono', monospace", color: "var(--text3)" }}>{f.field}</code>
            {" = "}<strong>{f.value}</strong>
          </span>
          <LiftHint value={f.lift ?? 1} prefix="" />
        </div>
      ))}

      {(base || lifts.length > 0) && (
        <div style={{
          marginTop: 2, padding: "8px 10px",
          background: "var(--surface)", borderRadius: 4,
          display: "flex", alignItems: "baseline", justifyContent: "center", flexWrap: "wrap",
          fontSize: 12, color: "var(--text2)", gap: 4,
          fontFamily: "'IBM Plex Mono', monospace",
        }}>
          <span>{(baseP * 100).toFixed(0)}%</span>
          {lifts.map((lift, i) => (
            <span key={i}> × {lift.toFixed(1)}</span>
          ))}
          <span style={{ color: "var(--text3)" }}> = </span>
          <span style={{ fontWeight: 700, color: "var(--gold-dark)" }}>{(confidence * 100).toFixed(0)}%</span>
        </div>
      )}
    </div>
  );
}
