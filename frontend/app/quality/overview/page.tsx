"use client";

import { useState, useEffect } from "react";
import Nav from "@/components/shell/Nav";
import TopBar from "@/components/shell/TopBar";
import AitoPanel from "@/components/shell/AitoPanel";
import { apiFetch } from "@/lib/api";
import type { AitoPanelConfig } from "@/lib/types";

const PANEL: AitoPanelConfig = {
  operation: "_search (aggregates)",
  stats: [
    { value: "78%", label: "Automation" },
    { value: "63%", label: "Aito share" },
    { value: "230", label: "Records" },
    { value: "Zero", label: "Training" },
  ],
  description: "Quality overview aggregates from the invoices and overrides tables. Automation breakdown computed from routed_by field.",
  query: JSON.stringify({ from: "invoices", where: {}, limit: 300 }, null, 2),
  links: [{ label: "Quality monitoring docs", url: "https://aito.ai/docs" }],
};

interface QualityData {
  automation: { total: number; rule: number; aito: number; human: number; rule_pct: number; aito_pct: number; human_pct: number; automation_rate: number };
  overrides: { total: number; by_field: Record<string, number> };
  override_patterns: { corrected_to: string; field: string; count: number; lift: number }[];
}

function BarRow({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const pct = max > 0 ? (value / max) * 100 : 0;
  return (
    <div className="bar-row">
      <div className="bar-label">{label}</div>
      <div className="bar-track"><div className={`bar-fill ${color}`} style={{ width: `${pct}%` }} /></div>
      <div className="bar-val">{value}%</div>
    </div>
  );
}

export default function QualityOverviewPage() {
  const [data, setData] = useState<QualityData | null>(null);
  const [live, setLive] = useState(false);

  useEffect(() => {
    apiFetch<QualityData>("/api/quality/overview")
      .then((d) => { setData(d); setLive(true); })
      .catch(() => {});
  }, []);

  const a = data?.automation;

  return (
    <>
      <Nav />
      <div className="main">
        <TopBar breadcrumb="Quality" title="System Overview" subtitle="Automation breakdown from live data" live={live} />
        <div className="content">
          <div className="metrics">
            <div className="metric highlight"><div className="metric-label">Overall automation</div><div className="metric-value">{a ? `${a.automation_rate}%` : "--"}</div><div className="metric-sub metric-up">{a ? `\u2191 from ${a.rule_pct}% rules-only` : ""}</div></div>
            <div className="metric"><div className="metric-label">Rules coverage</div><div className="metric-value">{a?.rule_pct ?? "--"}%</div><div className="metric-sub metric-neutral">{a?.rule ?? "--"} rule-routed</div></div>
            <div className="metric"><div className="metric-label">Aito coverage</div><div className="metric-value">{a?.aito_pct ?? "--"}%</div></div>
            <div className="metric"><div className="metric-label">Human review</div><div className="metric-value">{a?.human_pct ?? "--"}%</div></div>
          </div>
          <div className="quality-grid">
            <div className="quality-card">
              <div className="qc-header"><span className="qc-title">Processing source breakdown</span></div>
              <div className="qc-body">
                {a && (
                  <div style={{ display: "flex", height: 24, borderRadius: 4, overflow: "hidden", gap: 1, marginBottom: 16 }}>
                    <div style={{ width: `${a.rule_pct}%`, background: "var(--blue)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, color: "#fff", fontWeight: 500 }}>Rules {a.rule_pct}%</div>
                    <div style={{ width: `${a.aito_pct}%`, background: "var(--gold-mid)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, color: "#0d1520", fontWeight: 500 }}>Aito {a.aito_pct}%</div>
                    <div style={{ width: `${a.human_pct}%`, background: "var(--border2)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, color: "var(--text3)", fontWeight: 500 }}>{a.human_pct}%</div>
                  </div>
                )}
                <div style={{ fontSize: "11.5px", color: "var(--text3)", lineHeight: 1.6 }}>
                  Rules are precise but cover only {a?.rule_pct ?? "..."}% of cases. Aito extends coverage to {a?.automation_rate ?? "..."}% total.
                </div>
              </div>
            </div>
            <div className="quality-card">
              <div className="qc-header"><span className="qc-title">Override summary</span></div>
              <div className="qc-body">
                <div style={{ fontSize: 24, fontWeight: 600, fontFamily: "'IBM Plex Mono', monospace", marginBottom: 12 }}>{data?.overrides.total ?? "--"}</div>
                <div style={{ fontSize: 11, color: "var(--text3)", marginBottom: 12 }}>total overrides</div>
                {data && Object.entries(data.overrides.by_field).sort(([,a],[,b]) => b - a).map(([field, count]) => (
                  <div key={field} className="bar-row">
                    <div className="bar-label">{field}</div>
                    <div className="bar-track"><div className="bar-fill bar-fill-gold" style={{ width: `${(count / data.overrides.total) * 100}%` }} /></div>
                    <div className="bar-val">{count}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
      <AitoPanel config={PANEL} />
    </>
  );
}
