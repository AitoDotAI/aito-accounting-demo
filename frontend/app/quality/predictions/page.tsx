"use client";

import { useState, useEffect } from "react";
import Nav from "@/components/shell/Nav";
import { useCustomer } from "@/lib/customer-context";
import TopBar from "@/components/shell/TopBar";
import AitoPanel from "@/components/shell/AitoPanel";
import ErrorState from "@/components/shell/ErrorState";
import { apiFetch } from "@/lib/api";
import type { AitoPanelConfig } from "@/lib/types";

const PANEL: AitoPanelConfig = {
  operation: "_predict · _evaluate",
  stats: [{ value: "--", label: "Accuracy" }, { value: "--", label: "High-conf" }, { value: "--", label: "Dangerous" }, { value: "Indexed", label: "Model" }],
  description: "Real prediction accuracy computed by predicting GL codes and approvers on a sample of invoices and comparing to ground truth.",
  query: JSON.stringify({ from: "invoices", where: { vendor: { $get: "vendor" }, amount: { $get: "amount" } }, predict: "gl_code" }, null, 2),
  links: [{ label: "Confidence thresholds", url: "https://aito.ai/docs" }],
};

interface ConfBand {
  range: string;
  volume: string;
  accuracy: number;
  count: number;
}

interface PredictionData {
  overall_accuracy: number;
  gl_accuracy: number;
  approver_accuracy: number;
  override_rate: number;
  dangerous_errors: number;
  high_conf_accuracy: number;
  base_accuracy?: number;
  rules_coverage?: number;
  rules_accuracy_within?: number;
  rules_total_accuracy?: number;
  confidence_table: ConfBand[];
  accuracy_by_type: { label: string; value: number }[];
  total_evaluated: number;
}

function badgeClass(accuracy: number): string {
  if (accuracy >= 90) return "badge-green";
  if (accuracy >= 70) return "badge-amber";
  return "badge-red";
}

export default function PredictionQualityPage() {
  const { customerId } = useCustomer();
  const [data, setData] = useState<PredictionData | null>(null);
  const [live, setLive] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    apiFetch<PredictionData>(`/api/quality/predictions?customer_id=${customerId}`)
      .then((d) => { setData(d); setLive(true); })
      .catch(() => setError(true));
  }, [customerId]);

  return (
    <>
      <Nav />
      <div className="main">
        <TopBar
          breadcrumb="Quality"
          title="Prediction Quality"
          subtitle={data ? `Measured on ${data.total_evaluated} invoices against ground truth` : error ? "Backend not reachable" : "Loading..."}
          live={live}
        />
        <div className="content">
          <div className="metrics">
            <div className="metric highlight"><div className="metric-label">Overall accuracy</div><div className="metric-value">{data ? `${data.overall_accuracy}%` : "--"}</div><div className="metric-sub metric-up">{data ? `${data.total_evaluated} evaluated` : ""}</div></div>
            <div className="metric"><div className="metric-label">High-conf accuracy</div><div className="metric-value">{data ? `${data.high_conf_accuracy}%` : "--"}</div><div className="metric-sub metric-neutral">p &gt; 0.85</div></div>
            <div className="metric"><div className="metric-label">Override rate</div><div className="metric-value">{data ? `${data.override_rate}%` : "--"}</div></div>
            <div className="metric"><div className="metric-label">Dangerous errors</div><div className="metric-value">{data ? `${data.dangerous_errors}%` : "--"}</div><div className="metric-sub metric-neutral">High-conf wrong pred.</div></div>
          </div>
          {error && <ErrorState />}
          {data && data.rules_coverage != null && (
            <div style={{ background: "var(--surface2)", border: "1px solid var(--border2)", borderRadius: 8, padding: "16px 20px", marginBottom: 16 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", marginBottom: 12 }}>
                Rules-only baseline vs Aito
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
                <div>
                  <div style={{ fontSize: 11, color: "var(--text3)", marginBottom: 4 }}>Rules-only</div>
                  <div style={{ fontSize: 22, fontFamily: "'IBM Plex Mono', monospace", fontWeight: 600 }}>
                    {data.rules_coverage}% <span style={{ fontSize: 12, color: "var(--text3)" }}>covered</span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text2)", marginTop: 4 }}>
                    {data.rules_accuracy_within}% accurate within covered &middot; {data.rules_total_accuracy}% overall
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 11, color: "var(--gold-dark)", marginBottom: 4, fontWeight: 600 }}>With Aito</div>
                  <div style={{ fontSize: 22, fontFamily: "'IBM Plex Mono', monospace", fontWeight: 600, color: "var(--gold-dark)" }}>
                    100% <span style={{ fontSize: 12, color: "var(--text3)" }}>covered</span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text2)", marginTop: 4 }}>
                    {data.overall_accuracy}% accurate overall &middot; closes the {Math.max(0, 100 - (data.rules_coverage ?? 0))}pp coverage gap
                  </div>
                </div>
              </div>
            </div>
          )}
          {data && (
            <div className="quality-grid">
              <div className="quality-card">
                <div className="qc-header"><span className="qc-title">Accuracy by prediction type</span></div>
                <div className="qc-body">
                  {data.accuracy_by_type.map((a) => (
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
                      {data.confidence_table.map((row) => (
                        <tr key={row.range} style={{ borderTop: "1px solid var(--border2)" }}>
                          <td style={{ padding: "9px 0", fontFamily: "'IBM Plex Mono', monospace", fontSize: 12 }}>{row.range}</td>
                          <td style={{ textAlign: "right", padding: "9px 8px", color: "var(--text3)" }}>{row.volume}</td>
                          <td style={{ textAlign: "right", padding: "9px 0" }}><span className={`badge ${badgeClass(row.accuracy)}`}>{row.accuracy}%</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
      <AitoPanel config={PANEL} />
    </>
  );
}
