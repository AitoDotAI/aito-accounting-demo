"use client";

import { useState, useRef, useEffect } from "react";
import type { Alternative } from "@/lib/types";

interface PredictionBadgeProps {
  value: string;
  confidence: number;
  alternatives?: Alternative[];
  onSelect?: (alt: Alternative) => void;
}

export default function PredictionBadge({ value, confidence, alternatives, onSelect }: PredictionBadgeProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const hasAlts = alternatives && alternatives.length > 1;

  return (
    <div ref={ref} style={{ position: "relative", display: "inline-block" }}>
      <span
        className="pred-badge"
        onClick={() => hasAlts && setOpen(!open)}
        style={hasAlts ? {} : { cursor: "default" }}
      >
        {value}
        {hasAlts && <span style={{ fontSize: 9, opacity: 0.6 }}>{open ? "\u25B4" : "\u25BE"}</span>}
      </span>

      {open && alternatives && (
        <div className="alternatives-dropdown">
          {alternatives.map((alt, i) => (
            <div
              key={i}
              className={`alt-item ${alt.value === value ? "selected" : ""}`}
              onClick={() => {
                onSelect?.(alt);
                setOpen(false);
              }}
            >
              <span>{alt.display || alt.value}</span>
              <span className="conf-val" style={{ fontSize: 11 }}>
                {(alt.confidence * 100).toFixed(1)}%
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
