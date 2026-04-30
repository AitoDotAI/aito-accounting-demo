"use client";

import { useGuidedTour } from "@/lib/guided-tour";

export default function StartTourButton() {
  const { active, start } = useGuidedTour();
  if (active) return null;
  return (
    <button
      onClick={start}
      title="4 stops · under 5 minutes"
      style={{
        padding: "5px 10px",
        borderRadius: 6,
        border: "1px solid var(--gold-dark)",
        fontSize: 11,
        fontFamily: "inherit",
        background: "var(--gold-light)",
        color: "var(--gold-dark)",
        cursor: "pointer",
        fontWeight: 600,
      }}
    >
      ★ Start tour
    </button>
  );
}
