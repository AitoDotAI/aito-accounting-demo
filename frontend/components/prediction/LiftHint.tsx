"use client";

interface LiftHintProps {
  /** Multiplier value, e.g. 38 means "38×" */
  value: number;
  /** Optional prefix text, default "lift " */
  prefix?: string;
}

/**
 * Format a lift for display. Exported because the multiplication chain in
 * WhyCards prints the same numbers as the cards above it, and two copies
 * of these rules drifted: a lift of 28.29 showed as "28×" on the card and
 * "28.3" in the chain, one line apart.
 *
 * A strong counter-evidence lift can be 3.4e-06, and toFixed(1) prints that
 * as "0.0", which reads as a broken value rather than a very small one.
 */
export function formatLift(value: number): string {
  if (value > 0 && value < 0.05) return "<0.05";
  if (value < 10) return value.toFixed(1);
  return Math.round(value).toString();
}

/**
 * Render a lift number with an explanatory tooltip. Lift = how many
 * times more often this combination occurs vs random expectation.
 * < 1 = anti-correlated, 1 = no signal, 5+ = strong, 20+ = very strong.
 */
export default function LiftHint({ value, prefix = "lift " }: LiftHintProps) {
  if (value == null || isNaN(value)) return null;
  const tone =
    value >= 20 ? "strong" :
    value >= 5 ? "good" :
    value >= 1 ? "weak" :
    "none";
  const color =
    tone === "strong" ? "var(--green)" :
    tone === "good" ? "var(--gold-dark)" :
    tone === "weak" ? "var(--text3)" :
    "var(--red)";
  const shown = formatLift(value);
  const tooltip =
    `Lift = how many times more often this combination occurs than random.\n` +
    `> 20× very strong · 5–20× strong · 1–5× weak · < 1× anti-correlated.\n` +
    `This is ${value.toPrecision(3)}× — ${tone}.`;
  return (
    <span title={tooltip} style={{ color, fontWeight: 600, cursor: "help", borderBottom: "1px dotted currentColor" }}>
      {prefix}{shown}×
    </span>
  );
}
