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
    { value: "Indexed", label: "Model" },
  ],
  description:
    'Two-pass <code style="font-size:11px;color:var(--aito-accent)">_relate</code> ' +
    'on the overrides table: pass 1 finds the most-corrected target ' +
    'values, pass 2 walks the schema link to <code>invoices.vendor</code> ' +
    'to discover which input drove the correction. Output rows have ' +
    'the same input&nbsp;&rarr;&nbsp;output shape as Rule Mining, so ' +
    'they can be promoted directly into the rules table.',
  query: JSON.stringify(
    {
      pass2_input_to_output: {
        from: "overrides",
        where: { field: "gl_code", corrected_value: "5400" },
        relate: "invoice_id.vendor",
      },
    },
    null, 2,
  ),
  links: [{ label: "API reference: _relate", url: "https://aito.ai/docs/api/#post-api-v1-relate" }],
};

interface QualityData {
  automation: { automation_rate: number };
  overrides: { total: number; by_field: Record<string, number>; by_corrector: Record<string, number> };
  override_patterns: {
    corrected_to: string;
    field: string;
    count: number;
    lift: number;
    input_field?: string | null;
    input_value?: string | null;
  }[];
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
                {patterns.map((p, i) => {
                  const inputField = p.input_field?.replace(/^invoice_id\./, "");
                  return (
                    <div key={i} className="rule-row" style={{ padding: "10px 0" }}>
                      <div style={{ flex: 1 }}>
                        <div className="rule-pattern" style={{ fontSize: 13 }}>
                          {p.input_value ? (
                            <>
                              <code style={{ fontFamily: "'IBM Plex Mono', monospace", color: "var(--text3)" }}>
                                {inputField}
                              </code>
                              {" = "}
                              <strong>{p.input_value}</strong>
                              <span style={{ color: "var(--text3)", margin: "0 8px" }}>&rarr;</span>
                            </>
                          ) : null}
                          <code style={{ fontFamily: "'IBM Plex Mono', monospace", color: "var(--text3)" }}>
                            {p.field}
                          </code>
                          {" corrected to "}
                          <strong style={{ color: "var(--gold-dark)" }}>{p.corrected_to}</strong>
                        </div>
                        <div className="rule-arrow" style={{ marginTop: 3, fontSize: 11, color: "var(--text3)" }}>
                          {p.count} matching overrides &middot; <LiftHint value={p.lift} />
                          {p.input_value ? (
                            <span> &middot; via <code>_relate</code> on overrides linked to invoice.{inputField}</span>
                          ) : (
                            <span> &middot; not yet localised to a specific input</span>
                          )}
                        </div>
                      </div>
                      <span style={{ fontSize: 11, color: "var(--text3)", fontStyle: "italic", whiteSpace: "nowrap" }}>candidate rule</span>
                    </div>
                  );
                })}
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
