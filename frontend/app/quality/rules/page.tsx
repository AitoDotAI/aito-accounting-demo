"use client";

import Nav from "@/components/shell/Nav";
import TopBar from "@/components/shell/TopBar";
import AitoPanel from "@/components/shell/AitoPanel";
import ConfidenceBar from "@/components/prediction/ConfidenceBar";
import type { AitoPanelConfig } from "@/lib/types";

const PANEL: AitoPanelConfig = {
  operation: "_relate",
  stats: [{ value: "34", label: "Active" }, { value: "96%", label: "Precision" }, { value: "2", label: "Drifting" }, { value: "Zero", label: "Training" }],
  description: "Rule precision measured by replaying against human-verified decisions. Drift detected when precision drops.",
  query: JSON.stringify({ from: "invoices", where: { rule_fired: "telecom_fi" }, relate: "gl_code" }, null, 2),
  links: [{ label: "Rule evaluation docs", url: "https://aito.ai/docs" }],
};

const RULES = [
  { rule: 'vendor="Telia Finland"', fires: "GL 6200, Mikael H.", coverage: "6.2%", precision: 1.0, trend: "stable", status: "Active" },
  { rule: "amount < 50", fires: "GL 4500, auto", coverage: "5.1%", precision: 0.97, trend: "stable", status: "Active" },
  { rule: 'vendor_country="FI" AND cat="utilities"', fires: "GL 5100, Mikael H.", coverage: "3.8%", precision: 0.82, trend: "drifting", status: "Drifting" },
  { rule: 'vendor="Elisa Oyj"', fires: "GL 6200, auto", coverage: "2.1%", precision: 1.0, trend: "stable", status: "Active" },
  { rule: 'due_days=14 AND vendor_type="supplier"', fires: "GL 4400, Sanna L.", coverage: "1.4%", precision: 0.61, trend: "degrading", status: "Stale" },
];

export default function RulePerformancePage() {
  return (
    <>
      <Nav />
      <div className="main">
        <TopBar breadcrumb="Quality" title="Rule Performance" subtitle="34 active rules · 2 drifting · 1 stale" />
        <div className="content">
          <div className="card">
            <div className="card-header"><span className="card-title">All active rules</span><span className="card-hint">Precision measured against human-reviewed decisions</span></div>
            <table className="table">
              <thead><tr><th>Rule</th><th>Fires on</th><th>Coverage</th><th>Precision</th><th>Trend</th><th>Status</th></tr></thead>
              <tbody>
                {RULES.map((r, i) => (
                  <tr key={i}>
                    <td className="mono" style={{ fontSize: 11 }}>{r.rule}</td>
                    <td style={{ fontSize: 12 }}>{r.fires}</td>
                    <td className="mono">{r.coverage}</td>
                    <td><ConfidenceBar value={r.precision} /></td>
                    <td style={{ fontSize: 12, color: r.trend === "stable" ? "var(--green)" : r.trend === "drifting" ? "var(--amber)" : "var(--red)" }}>
                      {r.trend === "stable" ? "\u2192 stable" : `\u2193 ${r.trend}`}
                    </td>
                    <td>
                      <span className={`badge ${r.status === "Active" ? "badge-green" : r.status === "Drifting" ? "badge-amber" : "badge-red"}`}>{r.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      <AitoPanel config={PANEL} />
    </>
  );
}
