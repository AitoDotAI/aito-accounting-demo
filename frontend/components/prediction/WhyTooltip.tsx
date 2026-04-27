"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import type { WhyFactor } from "@/lib/types";

interface WhyTooltipProps {
  label: string;
  factors: WhyFactor[];
}

export default function WhyTooltip({ label, factors }: WhyTooltipProps) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);

  const updatePosition = useCallback(() => {
    if (!btnRef.current) return;
    const rect = btnRef.current.getBoundingClientRect();
    setPos({
      top: rect.top - 8,
      left: rect.left + rect.width / 2,
    });
  }, []);

  useEffect(() => {
    if (!open) return;
    updatePosition();
    function handleClick(e: MouseEvent) {
      if (
        popupRef.current && !popupRef.current.contains(e.target as Node) &&
        btnRef.current && !btnRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open, updatePosition]);

  if (!factors || factors.length === 0) return null;

  return (
    <>
      <button
        ref={btnRef}
        className="why-btn"
        onClick={() => setOpen(!open)}
        title="Why this prediction?"
      >
        ?
      </button>
      {open && pos && createPortal(
        <div
          ref={popupRef}
          className="why-popup"
          style={{
            position: "fixed",
            top: pos.top,
            left: pos.left,
            transform: "translate(-50%, -100%)",
          }}
        >
          <div className="why-title">Why {label}?</div>
          <div className="why-subtitle">Contributing factors from Aito $why</div>
          {factors.map((f, i) => <FactorRow key={i} f={f} />)}
          <div className="why-footer">
            Lift {">"} 1 means this feature makes the prediction more likely; base P is the prior probability of the predicted value.
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}

function FactorRow({ f }: { f: WhyFactor }) {
  // Base probability factor
  if (f.type === "base") {
    return (
      <div className="why-factor">
        <span className="why-factor-field">base P</span>
        <span className="why-factor-value">({f.target_value ?? ""})</span>
        <span className="why-factor-lift">{((f.base_p ?? 0) * 100).toFixed(1)}%</span>
      </div>
    );
  }
  // New grouped pattern shape
  if (f.type === "pattern" && f.propositions) {
    const liftStr = (f.lift ?? 1) > 1 ? `${(f.lift ?? 1).toFixed(1)}x` : `${(f.lift ?? 1).toFixed(2)}x`;
    return (
      <div className="why-factor" style={{ alignItems: "flex-start" }}>
        <span className="why-factor-field" style={{ minWidth: 0, maxWidth: "70%" }}>
          {f.propositions.map((p, pi) => (
            <span key={pi} style={{ display: "block", lineHeight: 1.4 }}>
              {p.field.replace(/^invoice_id\./, "")}
              {p.highlight ? " contains " : " = "}
              {p.highlight ? (
                <span dangerouslySetInnerHTML={{ __html: p.highlight }} />
              ) : (
                <strong>{p.value}</strong>
              )}
            </span>
          ))}
        </span>
        <span className="why-factor-lift">{liftStr}</span>
      </div>
    );
  }
  // Legacy flat shape
  return (
    <div className="why-factor">
      <span className="why-factor-field">{f.field}</span>
      <span className="why-factor-value">= &quot;{f.value}&quot;</span>
      <span className="why-factor-lift">
        {(f.lift ?? 0) > 1 ? `${(f.lift ?? 0).toFixed(1)}x` : `${(f.lift ?? 0).toFixed(2)}x`}
      </span>
    </div>
  );
}
