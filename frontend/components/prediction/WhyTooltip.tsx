"use client";

import { useState } from "react";

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

  if (!factors || factors.length === 0) return null;

  return (
    <>
      <button
        className="why-btn"
        onClick={() => setOpen(!open)}
        title="Why this prediction?"
      >
        ?
      </button>
      {open && (
        <div className="why-panel">
          <div className="why-title">Why {label}?</div>
          {factors.map((f, i) => (
            <div key={i} className="why-factor">
              <span className="why-factor-field">{f.field}</span>
              <span className="why-factor-value">= &quot;{f.value}&quot;</span>
              <span className="why-factor-lift">
                {f.lift > 1 ? `${f.lift.toFixed(1)}x more likely` : `${f.lift.toFixed(2)}x`}
              </span>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
