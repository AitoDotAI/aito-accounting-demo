"use client";

import LiftHint, { formatLift } from "./LiftHint";
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
  blendNote,
  modelP,
  onHoverFactor,
}: {
  why: WhyFactor[];
  confidence: number;
  /**
   * Set when `confidence` is NOT the product of the factors above —
   * payment matching blends Aito's probability with an amount-proximity
   * score, so its final number cannot be reached by multiplying the
   * $why chain. The footer then shows the chain's own product and this
   * note explains the extra step, instead of printing an equals sign
   * between two unrelated quantities (which read as "0% × 0.7 = 58%").
   */
  blendNote?: string;
  /**
   * The model's own probability for this value, when the caller knows it.
   * `confidence` may be a blend of it with something else, so the factor
   * chain is a decomposition of THIS number rather than of `confidence`.
   */
  modelP?: number;
  onHoverFactor?: (h: HoverHighlight) => void;
}) {
  const base = why.find((f) => f.type === "base");
  const patterns = why.filter((f) => f.type === "pattern");
  // Aito's own normalisation terms (exclusiveness, rowCap). Real factors of
  // the model's product; dropping them made the printed chain short.
  const normalizers = why.filter((f) => f.type === "normalizer");
  const legacy = why.filter((f) => !f.type && f.field);  // old precomputed JSON

  const baseP = base?.base_p ?? 0;
  const lifts = patterns.map((p) => p.lift ?? 1);
  const hover = onHoverFactor ?? (() => {});

  // The chain's own result, including Aito's normalisation terms.
  const chainProduct = normalizers.reduce(
    (acc, n) => acc * (n.multiplier ?? 1),
    lifts.reduce((acc, l) => acc * l, baseP),
  );

  // Does the chain actually account for the model's probability?
  //
  // It is supposed to: on Aito 2.8.0 the factors multiplied to $p exactly.
  // On 2.8.1 they do not — 3.5% of factors against a reported 99.74%, a 28x
  // gap that is inside the response and not ours to close
  // (td-20260909133103405502). Printing "= 0.71%" under a 97% match is worse
  // than printing nothing: it invites the reader to check arithmetic that
  // cannot balance. So when the chain misses by more than half an order of
  // magnitude we show what the factors come to AND what the model said,
  // labelled, instead of asserting an equation between them.
  const reconciles =
    modelP == null ||
    modelP <= 0 ||
    (chainProduct > 0 && Math.abs(Math.log10(chainProduct / modelP)) < 0.5);

  // A link-target base rate is ~1/128000. Printing that as "0%" makes
  // the whole line read as broken, so show the smallest honest figure.
  const pct = (v: number) => {
    if (v > 0 && v < 0.0001) return "<0.01%";
    if (v > 0 && v < 0.01) return `${(v * 100).toFixed(2)}%`;
    return `${(v * 100).toFixed(0)}%`;
  };

  const summaryStyle = {
    marginTop: 2, padding: "8px 10px",
    background: "var(--surface)", borderRadius: 4,
    display: "flex", alignItems: "baseline", justifyContent: "center", flexWrap: "wrap",
    fontSize: 12, color: "var(--text2)", gap: 4,
    fontFamily: "'IBM Plex Mono', monospace",
  } as const;

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
            {pct(baseP)}
          </div>
        </div>
      )}

      {patterns.map((f, i) => {
        const lift = f.lift ?? 1;
        const negative = lift < 1;
        // Render rule: each "row" inside a pattern card corresponds to
        // one input field. Source of truth:
        //   - highlights[] when Aito returned them (text fields with
        //     analyzer matches): show the full context with <mark>
        //     tokens already inserted by Aito.
        //   - propositions[] otherwise (categorical fields): show
        //     "field = value".
        // We dedupe propositions by field so multi-token text matches
        // (e.g. description $has "office" + description $has "supplies")
        // collapse into the single highlight Aito returned for the
        // description field.
        const highlightFields = new Set((f.highlights ?? []).map((h) => h.field));
        const propsByField = new Map<string, string>();
        for (const p of f.propositions ?? []) {
          if (highlightFields.has(p.field)) continue;
          if (!propsByField.has(p.field)) propsByField.set(p.field, p.value);
        }
        const rows: { field: string; render: () => React.ReactNode }[] = [
          ...(f.highlights ?? []).map((h) => ({
            field: h.field,
            render: () => <span dangerouslySetInnerHTML={{ __html: h.html }} />,
          })),
          ...Array.from(propsByField.entries()).map(([field, value]) => ({
            field,
            render: () => <strong>{value}</strong>,
          })),
        ];
        const firstField = rows[0]?.field ?? null;

        return (
          <div
            key={i}
            onMouseEnter={() => hover({ field: firstField, value: null })}
            onMouseLeave={() => hover({ field: null, value: null })}
            style={{
              background: negative ? "rgba(220, 53, 69, 0.06)" : "var(--gold-light)",
              borderLeft: `3px solid ${negative ? "var(--red)" : "var(--gold-dark)"}`,
              borderRadius: 4,
              padding: "8px 10px",
              display: "flex", justifyContent: "space-between", gap: 12,
              cursor: "default",
            }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{
                fontSize: 10,
                color: negative ? "var(--red)" : "var(--gold-dark)",
                textTransform: "uppercase", letterSpacing: ".6px", fontWeight: 600,
              }}>
                {negative ? "Counter-evidence" : "Pattern match"}
              </div>
              <div style={{ fontSize: 11, color: "var(--text2)", lineHeight: 1.55, marginTop: 2 }}>
                {rows.length === 0 ? null : (
                  <>
                    When{" "}
                    {rows.map((r, ri) => {
                      const sep = ri === 0 ? "" : ri === rows.length - 1 ? " and " : ", ";
                      const fieldLabel = r.field.replace(/^invoice_id\./, "");
                      return (
                        <span key={ri}>
                          {sep}
                          <code style={{ fontFamily: "'IBM Plex Mono', monospace", color: "var(--text3)" }}>{fieldLabel}</code>
                          {" is "}
                          {r.render()}
                        </span>
                      );
                    })}
                  </>
                )}
              </div>
            </div>
            <LiftHint value={lift} prefix="× " />
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

      {/* The chain needs a base probability to multiply. A same-vendor
          substitute has no `$why` of its own — see `_build_explanation`
          in src/matching_service.py — and rendering its missing base as
          "0%" printed "0% × 1.0 = 0%" underneath a 57% match. With no
          base there is no equation to show, only the number itself. */}
      {(base || (!blendNote && lifts.length > 0)) && (
        <div style={summaryStyle}>
          {base ? (
            <>
              <span>{pct(baseP)}</span>
              {normalizers.map((n, i) => (
                <span key={`n${i}`} title={n.name}> × {formatLift(n.multiplier ?? 1)}</span>
              ))}
              {lifts.map((lift, i) => (
                // formatLift, not a local rule: this chain restates the
                // numbers on the cards above, so both must round alike.
                <span key={i}> × {formatLift(lift)}</span>
              ))}
              <span style={{ color: "var(--text3)" }}>{reconciles ? " = " : " → "}</span>
              <span style={{ fontWeight: 700, color: "var(--gold-dark)" }}>
                {pct(reconciles && !blendNote ? confidence : chainProduct)}
              </span>
            </>
          ) : (
            <>
              <span style={{ color: "var(--text3)" }}>confidence </span>
              <span style={{ fontWeight: 700, color: "var(--gold-dark)" }}>
                {pct(confidence)}
              </span>
            </>
          )}
        </div>
      )}

      {/* The factors do not account for the model's probability. Say so,
          rather than leaving a reader to check arithmetic that cannot
          balance. Tracked as td-20260909133103405502. */}
      {!reconciles && modelP != null && (
        <div style={{
          padding: "6px 10px", fontSize: 11, color: "var(--text3)",
          borderTop: "1px dashed var(--border)", textAlign: "center",
        }}>
          These factors account for {pct(chainProduct)} of the model&rsquo;s{" "}
          <strong style={{ color: "var(--text2)" }}>{pct(modelP)}</strong>
          {" "}— Aito&rsquo;s explanation is currently incomplete, so the chain
          above is a partial decomposition rather than the whole calculation.
        </div>
      )}

      {blendNote && (
        <div style={{
          padding: "6px 10px", fontSize: 11, color: "var(--text3)",
          borderTop: "1px dashed var(--border)", textAlign: "center",
        }}>
          {blendNote}{" "}
          <strong style={{ color: "var(--gold-dark)" }}>{pct(confidence)}</strong>
        </div>
      )}
    </div>
  );
}
