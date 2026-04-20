"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";

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
        </div>,
        document.body,
      )}
    </>
  );
}
