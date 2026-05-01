"use client";

import { useGuidedTour, TOUR_STOPS } from "@/lib/guided-tour";

/**
 * Floating tour panel pinned bottom-center. Persists across page
 * navigations because it lives at the layout level and reads its
 * state from a context that survives via localStorage. No Aito calls,
 * just narration — under 5 minutes for a fresh visitor.
 */
export default function GuidedTourOverlay() {
  const { active, step, next, prev, end } = useGuidedTour();
  if (!active) return null;
  const stop = TOUR_STOPS[step];
  const last = step === TOUR_STOPS.length - 1;
  const first = step === 0;

  return (
    <div
      style={{
        position: "fixed",
        left: "50%",
        bottom: 18,
        transform: "translateX(-50%)",
        width: "min(620px, calc(100vw - 32px))",
        background: "var(--surface)",
        border: "1px solid var(--gold-dark)",
        borderRadius: 10,
        boxShadow: "0 10px 32px rgba(0,0,0,.18)",
        zIndex: 1200,
        padding: "14px 18px",
        display: "flex",
        flexDirection: "column",
        gap: 10,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            width: 22,
            height: 22,
            borderRadius: "50%",
            background: "var(--gold-dark)",
            color: "#f5e8c0",
            fontSize: 11,
            fontWeight: 700,
            fontFamily: "'IBM Plex Mono', monospace",
            flexShrink: 0,
          }}
        >
          {stop.n}
        </span>
        <span style={{ fontSize: 10, fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px" }}>
          Guided tour · {stop.n} of {TOUR_STOPS.length}
        </span>
        <button
          onClick={end}
          style={{
            marginLeft: "auto",
            background: "transparent",
            border: "none",
            color: "var(--text3)",
            fontSize: 18,
            cursor: "pointer",
            lineHeight: 1,
            padding: "0 4px",
            fontFamily: "inherit",
          }}
          title="Exit tour"
          aria-label="Exit tour"
        >
          ×
        </button>
      </div>
      <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text)", lineHeight: 1.4 }}>
        {stop.title}
      </div>
      <div style={{ fontSize: 12.5, color: "var(--text2)", lineHeight: 1.6 }}>
        {stop.pitch}
      </div>
      <div
        style={{
          fontSize: 11.5,
          color: "var(--gold-dark)",
          background: "var(--gold-light)",
          border: "1px solid #e0cc88",
          borderRadius: 6,
          padding: "7px 10px",
          lineHeight: 1.5,
        }}
      >
        <strong>Try it:</strong> {stop.action}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <code style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10.5, color: "var(--text3)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {stop.call}
        </code>
        <button
          onClick={prev}
          disabled={first}
          style={{
            padding: "6px 12px",
            fontSize: 12,
            border: "1px solid var(--border)",
            background: first ? "var(--surface2)" : "var(--surface)",
            color: first ? "var(--text3)" : "var(--text2)",
            borderRadius: 5,
            cursor: first ? "not-allowed" : "pointer",
            fontFamily: "inherit",
          }}
        >
          ← Back
        </button>
        <button
          onClick={last ? end : next}
          style={{
            padding: "6px 14px",
            fontSize: 12,
            border: "none",
            background: "var(--gold-dark)",
            color: "#f5e8c0",
            borderRadius: 5,
            cursor: "pointer",
            fontFamily: "inherit",
            fontWeight: 600,
          }}
        >
          {last ? "Finish" : "Next →"}
        </button>
      </div>
    </div>
  );
}
