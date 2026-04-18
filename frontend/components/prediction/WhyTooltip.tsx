"use client";

import { useState, useRef, useEffect } from "react";

interface WhyFactor {
  field: string;
  value: string;
  lift: number;
}

interface WhyTooltipProps {
  label: string;
  factors: WhyFactor[];
}

export default function WhyTooltip({ label, factors }: WhyTooltipProps) {
  const [open, setOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (
        popupRef.current && !popupRef.current.contains(e.target as Node) &&
        btnRef.current && !btnRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  if (!factors || factors.length === 0) return null;

  return (
    <span style={{ position: "relative", display: "inline-flex" }}>
      <button
        ref={btnRef}
        className="why-btn"
        onClick={() => setOpen(!open)}
        title="Why this prediction?"
      >
        ?
      </button>
      {open && (
        <div ref={popupRef} className="why-popup">
          <div className="why-title">Why {label}?</div>
          <div className="why-subtitle">Contributing factors from Aito $why</div>
          {factors.map((f, i) => (
            <div key={i} className="why-factor">
              <span className="why-factor-field">{f.field}</span>
              <span className="why-factor-value">= &quot;{f.value}&quot;</span>
              <span className="why-factor-lift">
                {f.lift > 1 ? `${f.lift.toFixed(1)}x` : `${f.lift.toFixed(2)}x`}
              </span>
            </div>
          ))}
          <div className="why-footer">
            Lift {">"} 1 means this feature makes the prediction more likely
          </div>
        </div>
      )}
    </span>
  );
}
