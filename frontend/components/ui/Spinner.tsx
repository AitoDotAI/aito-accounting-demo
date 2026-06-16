"use client";

interface SpinnerProps {
  /** Edge length in px. Defaults to 12 (matches inline text height). */
  size?: number;
  /** Optional accessible label. Decorative by default. */
  label?: string;
}

/**
 * Inline spinner. CSS-only, sized to sit next to text. Use when an
 * async call is in flight and the user might otherwise wonder whether
 * the page has updated yet.
 */
export default function Spinner({ size = 12, label }: SpinnerProps) {
  return (
    <span
      className="ui-spinner"
      role={label ? "status" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      style={{ width: size, height: size }}
    />
  );
}
