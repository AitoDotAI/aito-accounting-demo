"use client";

import { useState, useEffect } from "react";
import Nav from "@/components/shell/Nav";
import { useCustomer } from "@/lib/customer-context";
import ErrorState from "@/components/shell/ErrorState";
import TopBar from "@/components/shell/TopBar";
import AitoPanel from "@/components/shell/AitoPanel";
import LiftHint from "@/components/prediction/LiftHint";
import { apiFetch } from "@/lib/api";
import type { AitoPanelConfig } from "@/lib/types";

const PANEL: AitoPanelConfig = {
  operation: "_relate (override mining)",
  stats: [
    { value: "_relate", label: "Operation" },
    { value: "Live", label: "Predictions" },
    { value: "$invoices", label: "Records" },
    { value: "Zero", label: "Training" },
  ],
  description:
    'Every override is fed through <code style="font-size:11px;color:var(--aito-accent)">_relate</code> to find emerging patterns. ' +
    "Overrides are the primary signal for rule improvement — patterns surfaced here become rule candidates.",
  query: JSON.stringify(
    { from: "overrides", where: { field: "gl_code" }, relate: "corrected_value" },
    null, 2,
  ),
  links: [{ label: "API reference: _relate", url: "https://aito.ai/docs/api/#post-api-v1-relate" }],
};

interface QualityData {
  automation: { automation_rate: number };
  overrides: { total: number; by_field: Record<string, number>; by_corrector: Record<string, number> };
  override_patterns: { corrected_to: string; field: string; count: number; lift: number }[];
}

export default function OverridesPage() {
  const { customerId } = useCustomer();
  const [data, setData] = useState<QualityData | null>(null);
  const [live, setLive] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    setData(null); setLive(false); setError(false);
    apiFetch<QualityData>(`/api/quality/overview?customer_id=${customerId}`)
      .then((d) => { setData(d); setLive(true); })
      .catch(() => setError(true));
  }, [customerId]);

  const o = data?.overrides;
  const patterns = data?.override_patterns ?? [];
  const topPattern = patterns[0];

  return (
    <>
      <Nav />
      <div className="main">
        <TopBar breadcrumb="Quality" title="Human Overrides" subtitle="Every correction is a learning signal" live={live} />
        <div className="content">
          {topPattern && (
            <div style={{ background: "var(--gold-light)", border: "1px solid #d8bc70", borderRadius: 8, padding: "14px 18px", marginBottom: 16 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--gold-dark)", textTransform: "uppercase", letterSpacing: ".6px", marginBottom: 6 }}>
                Headline finding
              </div>
              <div style={{ fontSize: 14, color: "var(--text)", lineHeight: 1.6 }}>
                Reviewers corrected <strong>{topPattern.field}</strong> to{" "}
                <strong>{topPattern.corrected_to}</strong> in{" "}
                <strong>{topPattern.count}</strong> recent invoices
                {topPattern.lift > 1 && <> (<LiftHint value={topPattern.lift} /> over baseline)</>}.
                This is a rule candidate — promote it once support stabilises.
              </div>
            </div>
          )}
          <div className="metrics">
            <div className="metric highlight"><div className="metric-label">Overrides</div><div className="metric-value">{o?.total ?? "--"}</div></div>
            <div className="metric"><div className="metric-label">Patterns found</div><div className="metric-value">{patterns.length || "--"}</div><div className="metric-sub metric-neutral">Rule candidates</div></div>
            <div className="metric"><div className="metric-label">Most-overridden field</div><div className="metric-value" style={{ fontSize: 15 }}>{o && Object.keys(o.by_field).length > 0 ? Object.entries(o.by_field).sort(([,a],[,b]) => b - a)[0][0] : "—"}</div><div className="metric-sub metric-neutral">{o?.by_field && Object.entries(o.by_field).sort(([,a],[,b]) => b - a)[0]?.[1]} corrections</div></div>
            <div className="metric"><div className="metric-label">Active correctors</div><div className="metric-value">{o?.by_corrector ? Object.keys(o.by_corrector).length : "--"}</div></div>
          </div>
          <div className="quality-grid">
            <div className="quality-card">
              <div className="qc-header"><span className="qc-title">Emerging patterns from overrides</span><span className="card-hint">From <code>_relate</code> on overrides</span></div>
              <div className="qc-body">
                {patterns.length === 0 && <div style={{ color: "var(--text3)", fontSize: 12, lineHeight: 1.6 }}>No patterns found yet — patterns surface once 5+ overrides target the same value.</div>}
                {patterns.map((p, i) => (
                  <div key={i} className="rule-row" style={{ padding: "10px 0" }}>
                    <div style={{ flex: 1 }}>
                      <div className="rule-pattern">{p.field} &rarr; {p.corrected_to}</div>
                      <div className="rule-arrow" style={{ marginTop: 3, fontSize: 11, color: "var(--text3)" }}>{p.count} overrides &middot; <LiftHint value={p.lift} /></div>
                    </div>
                    <span style={{ fontSize: 11, color: "var(--text3)", fontStyle: "italic" }}>candidate rule</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="quality-card">
              <div className="qc-header"><span className="qc-title">Overrides by field type</span></div>
              <div className="qc-body">
                {o && Object.entries(o.by_field).sort(([,a],[,b]) => b - a).map(([field, count]) => (
                  <div key={field} className="bar-row">
                    <div className="bar-label">{field}</div>
                    <div className="bar-track"><div className="bar-fill bar-fill-gold" style={{ width: `${(count / o.total) * 100}%` }} /></div>
                    <div className="bar-val">{count}</div>
                  </div>
                ))}
              </div>
            </div>
            {o?.by_corrector && (
              <div className="quality-card">
                <div className="qc-header"><span className="qc-title">Overrides by corrector</span></div>
                <div className="qc-body">
                  {Object.entries(o.by_corrector).sort(([,a],[,b]) => b - a).map(([name, count]) => (
                    <div key={name} className="bar-row">
                      <div className="bar-label">{name}</div>
                      <div className="bar-track"><div className="bar-fill bar-fill-blue" style={{ width: `${(count / o.total) * 100}%` }} /></div>
                      <div className="bar-val">{count}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
      <AitoPanel config={PANEL} />
    </>
  );
}
