import { confClass } from "@/lib/api";

export default function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div className="conf">
      <div className="conf-bar">
        <div className={`conf-fill ${confClass(value)}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="conf-val">{value.toFixed(2)}</span>
    </div>
  );
}
