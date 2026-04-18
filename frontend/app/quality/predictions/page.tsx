"use client";

import Nav from "@/components/shell/Nav";
import TopBar from "@/components/shell/TopBar";
import AitoPanel from "@/components/shell/AitoPanel";
import type { AitoPanelConfig } from "@/lib/types";

const PANEL: AitoPanelConfig = {
  operation: "_predict · $p · $why",
  stats: [{ value: "94%", label: "Accuracy" }, { value: "98%", label: "High-conf" }, { value: "0.4%", label: "Dangerous" }, { value: "Zero", label: "Training" }],
  description: "Prediction quality by confidence band. The confidence-accuracy table shows where to set the auto-approve threshold.",
  query: JSON.stringify({ from: "predictions", where: { "$p": { "$gte": 0.85 } }, select: ["$p", "predicted", "actual"] }, null, 2),
  links: [{ label: "Confidence thresholds", url: "https://aito.ai/docs" }],
};

const ACCURACY_BY_TYPE = [
  { label: "GL code", value: 91 },
  { label: "Approver routing", value: 96 },
  { label: "VAT rate", value: 99 },
  { label: "Due date", value: 94 },
  { label: "Cost centre", value: 88 },
  { label: "Payment method", value: 97 },
];

const CONF_TABLE = [
  { range: "0.95 \u2013 1.00", volume: "38%", accuracy: 99.1, badge: "badge-green" },
  { range: "0.85 \u2013 0.95", volume: "36%", accuracy: 96.4, badge: "badge-green" },
  { range: "0.70 \u2013 0.85", volume: "17%", accuracy: 84.2, badge: "badge-amber" },
  { range: "0.50 \u2013 0.70", volume: "6%", accuracy: 71.8, badge: "badge-amber" },
  { range: "< 0.50", volume: "3%", accuracy: 48.3, badge: "badge-red" },
];

export default function PredictionQualityPage() {
  return (
    <>
      <Nav />
      <div className="main">
        <TopBar breadcrumb="Quality" title="Prediction Quality" subtitle="Measured against verified human decisions" />
        <div className="content">
          <div className="metrics">
            <div className="metric highlight"><div className="metric-label">Overall accuracy</div><div className="metric-value">94%</div><div className="metric-sub metric-up">vs 67% RF baseline</div></div>
            <div className="metric"><div className="metric-label">High-conf accuracy</div><div className="metric-value">98%</div><div className="metric-sub metric-neutral">p &gt; 0.85 &middot; 74% of cases</div></div>
            <div className="metric"><div className="metric-label">Override rate</div><div className="metric-value">6%</div><div className="metric-sub metric-up">&darr; 4pp this month</div></div>
            <div className="metric"><div className="metric-label">Dangerous errors</div><div className="metric-value">0.4%</div><div className="metric-sub metric-neutral">High-conf wrong pred.</div></div>
          </div>
          <div className="quality-grid">
            <div className="quality-card">
              <div className="qc-header"><span className="qc-title">Accuracy by prediction type</span></div>
              <div className="qc-body">
                {ACCURACY_BY_TYPE.map((a) => (
                  <div key={a.label} className="bar-row">
                    <div className="bar-label">{a.label}</div>
                    <div className="bar-track"><div className="bar-fill bar-fill-green" style={{ width: `${a.value}%` }} /></div>
                    <div className="bar-val">{a.value}%</div>
                  </div>
                ))}
              </div>
            </div>
            <div className="quality-card">
              <div className="qc-header"><span className="qc-title">Accuracy vs confidence threshold</span></div>
              <div className="qc-body">
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ fontSize: "10.5px", color: "var(--text3)" }}>
                      <th style={{ textAlign: "left", padding: "4px 0", fontWeight: 600, textTransform: "uppercase", letterSpacing: ".6px" }}>Confidence range</th>
                      <th style={{ textAlign: "right", padding: "4px 8px", fontWeight: 600, textTransform: "uppercase", letterSpacing: ".6px" }}>Volume</th>
                      <th style={{ textAlign: "right", padding: "4px 0", fontWeight: 600, textTransform: "uppercase", letterSpacing: ".6px" }}>Accuracy</th>
                    </tr>
                  </thead>
                  <tbody>
                    {CONF_TABLE.map((row) => (
                      <tr key={row.range} style={{ borderTop: "1px solid var(--border2)" }}>
                        <td style={{ padding: "9px 0", fontFamily: "'IBM Plex Mono', monospace", fontSize: 12 }}>{row.range}</td>
                        <td style={{ textAlign: "right", padding: "9px 8px", color: "var(--text3)" }}>{row.volume}</td>
                        <td style={{ textAlign: "right", padding: "9px 0" }}><span className={`badge ${row.badge}`}>{row.accuracy}%</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div style={{ marginTop: 12, fontSize: "11.5px", color: "var(--text3)", lineHeight: 1.6 }}>
                  Setting auto-approve threshold at 0.85 captures 74% of cases at 97%+ accuracy.
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <AitoPanel config={PANEL} />
    </>
  );
}
