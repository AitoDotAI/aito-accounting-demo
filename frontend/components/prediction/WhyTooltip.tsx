"use client";

import { useState, useRef, useEffect, useLayoutEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import WhyCards from "./WhyCards";
import { placePopup, type Placement } from "@/lib/popup-placement";
import type { WhyFactor } from "@/lib/types";

interface WhyTooltipProps {
  label: string;
  factors: WhyFactor[];
  /** Top prediction's $p — drives the calculation summary in WhyCards. */
  confidence?: number;
}

export default function WhyTooltip({ label, factors, confidence = 0 }: WhyTooltipProps) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<Placement | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);

  const POPUP_WIDTH = 380;

  // Place from the popup's MEASURED height. It used to open above the
  // button unconditionally with no height limit, so on rows in the upper
  // part of the screen its top was cut off by the viewport edge. See
  // lib/popup-placement.ts.
  const updatePosition = useCallback(() => {
    if (!btnRef.current || !popupRef.current) return;
    const r = btnRef.current.getBoundingClientRect();
    setPos(placePopup(
      { top: r.top, bottom: r.bottom, left: r.left, width: r.width },
      { width: POPUP_WIDTH, height: popupRef.current.scrollHeight },
      { width: window.innerWidth, height: window.innerHeight },
    ));
  }, []);

  // Measure before paint: the popup first renders hidden, then is placed.
  useLayoutEffect(() => {
    if (open) updatePosition();
    else setPos(null);
  }, [open, updatePosition]);

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
    window.addEventListener("scroll", updatePosition, true);
    window.addEventListener("resize", updatePosition);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      window.removeEventListener("scroll", updatePosition, true);
      window.removeEventListener("resize", updatePosition);
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
      {open && createPortal(
        <div
          ref={popupRef}
          className="why-popup"
          data-placement={pos?.placement ?? "above"}
          style={{
            // The arrow is CSS; it reads where to point from here.
            ["--arrow-x" as string]: `${pos?.arrowX ?? 190}px`,
            position: "fixed",
            top: pos?.top ?? 0,
            left: pos?.left ?? 0,
            // Hidden until measured and placed, so it never flashes
            // in the wrong spot.
            visibility: pos ? "visible" : "hidden",
            maxHeight: pos?.maxHeight,
            overflowY: pos?.maxHeight ? "auto" : undefined,
            // Wider than the legacy flat-list popup -- pattern cards
            // need horizontal room for the highlighted text spans.
            width: POPUP_WIDTH,
          }}
        >
          <div className="why-title">Why {label}?</div>
          <WhyCards why={factors} confidence={confidence} />
          <div className="why-footer" style={{ marginTop: 8 }}>
            Lift {">"} 1 means this feature makes the prediction more likely; base P is the prior probability of the predicted value.
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
