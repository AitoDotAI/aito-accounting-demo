"use client";

import WhyTooltip from "./WhyTooltip";

interface PredictedFieldProps {
  label: string;
  fieldName: string;
  value: string;
  predicted: boolean;
  confidence?: number;
  whyFactors?: { field: string; value: string; lift: number }[];
  highlightedFields?: Set<string>;
  onChange: (fieldName: string, value: string) => void;
  readOnly?: boolean;
}

export default function PredictedField({
  label,
  fieldName,
  value,
  predicted,
  confidence,
  whyFactors,
  highlightedFields,
  onChange,
  readOnly,
}: PredictedFieldProps) {
  const isHighlighted = highlightedFields?.has(fieldName);
  const inputClass = [
    "field-input",
    predicted ? "predicted" : "",
    isHighlighted ? "highlighted" : "",
  ].filter(Boolean).join(" ");

  return (
    <div className="field-group">
      <div className="field-label">{label}</div>
      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
        <input
          className={inputClass}
          value={value}
          onChange={(e) => onChange(fieldName, e.target.value)}
          readOnly={readOnly}
          placeholder={predicted ? "" : `Enter ${label.toLowerCase()}`}
        />
        {predicted && whyFactors && whyFactors.length > 0 && (
          <WhyTooltip label={value} factors={whyFactors} />
        )}
      </div>
      {predicted && confidence != null && (
        <div className="field-predicted-label">
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
            <path d="M2 5l2 2 4-4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
          </svg>
          Predicted &middot; {(confidence * 100).toFixed(1)}% confidence
        </div>
      )}
    </div>
  );
}
