"use client";

interface LiftHintProps {
  /** Multiplier value, e.g. 38 means "38×" */
  value: number;
  /** Optional prefix text, default "lift " */
  prefix?: string;
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
  // A strong counter-evidence lift can be 3.4e-06. toFixed(1) prints that
  // as "0.0", which reads as a broken value rather than a very small one.
  const shown =
    value > 0 && value < 0.05 ? "<0.05" :
    value < 10 ? value.toFixed(1) :
    Math.round(value).toString();
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
