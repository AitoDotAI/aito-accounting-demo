"use client";

import { useState, useEffect } from "react";
import Nav from "@/components/shell/Nav";
import { useCustomer } from "@/lib/customer-context";
import TopBar from "@/components/shell/TopBar";
import AitoPanel from "@/components/shell/AitoPanel";
import ConfidenceBar from "@/components/prediction/ConfidenceBar";
import ErrorState from "@/components/shell/ErrorState";
import { apiFetch } from "@/lib/api";
import type { AitoPanelConfig } from "@/lib/types";

const PANEL: AitoPanelConfig = {
  operation: "_predict (replay)",
  stats: [{ value: "--", label: "Rules" }, { value: "--", label: "Avg precision" }, { value: "Zero", label: "Training" }, { value: "100K", label: "Records" }],
  description: "Rule precision measured by replaying each rule against the full 100K invoice dataset and comparing to actual GL codes.",
  query: JSON.stringify({ from: "invoices", where: { vendor: "Telia Finland" }, predict: "gl_code" }, null, 2),
  links: [{ label: "Rule evaluation docs", url: "https://aito.ai/docs" }],
};

interface RulePerf {
  rule: string;
  fires_on: string;
  coverage: string;
  precision: number;
  total_matches: number;
  correct: number;
  trend: string;
  status: string;
}

interface RulesData {
  rules: RulePerf[];
}

export default function RulePerformancePage() {
  const { customerId } = useCustomer();
  const [data, setData] = useState<RulesData | null>(null);
  const [live, setLive] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    apiFetch<RulesData>(`/api/quality/rules?customer_id=${customerId}`)
      .then((d) => { setData(d); setLive(true); })
      .catch(() => setError(true));
  }, [customerId]);

  const rules = data?.rules ?? [];
  const avgPrecision = rules.length > 0
    ? rules.reduce((sum, r) => sum + r.precision, 0) / rules.length
    : 0;

  return (
    <>
      <Nav />
      <div className="main">
        <TopBar
          breadcrumb="Quality"
          title="Rule Performance"
          subtitle={data ? `${rules.length} rules evaluated against 100K invoices` : error ? "Backend not reachable" : "Loading..."}
          live={live}
        />
        <div className="content">
          {error && <ErrorState />}
          {data && (
            <div className="card">
              <div className="card-header">
                <span className="card-title">All rules — precision measured against ground truth</span>
                <span className="card-hint">Avg precision: {(avgPrecision * 100).toFixed(0)}%</span>
              </div>
              <table className="table">
                <thead>
                  <tr>
                    <th>Rule</th>
                    <th>Fires on</th>
                    <th>Coverage</th>
                    <th>Matches</th>
                    <th>Precision</th>
                    <th>Trend</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {rules.map((r, i) => (
                    <tr key={i}>
                      <td className="mono" style={{ fontSize: 11 }}>{r.rule}</td>
                      <td style={{ fontSize: 12 }}>{r.fires_on}</td>
                      <td className="mono">{r.coverage}</td>
                      <td className="mono">{r.total_matches.toLocaleString()}</td>
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
          )}
        </div>
      </div>
      <AitoPanel config={PANEL} />
    </>
  );
}
