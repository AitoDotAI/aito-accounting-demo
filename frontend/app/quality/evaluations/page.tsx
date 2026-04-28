"use client";

import { useState, useEffect } from "react";
import Nav from "@/components/shell/Nav";
import TopBar from "@/components/shell/TopBar";
import AitoPanel from "@/components/shell/AitoPanel";
import ErrorState from "@/components/shell/ErrorState";
import { useCustomer } from "@/lib/customer-context";
import { apiFetch } from "@/lib/api";
import type { AitoPanelConfig } from "@/lib/types";

const PANEL: AitoPanelConfig = {
  operation: "_evaluate (cross-validation)",
  stats: [
    { value: "_evaluate", label: "Operator" },
    { value: "Live", label: "Predictions" },
    { value: "$invoices", label: "Records" },
    { value: "Indexed", label: "Model" },
  ],
  description:
    'Aito\'s <code style="font-size:11px;color:var(--aito-accent)">_evaluate</code> runs leave-one-out cross-validation on a held-out test sample. ' +
    "One row per prediction task: GL code, approver, payment matching, help-article click. " +
    "Each task's row shows accuracy, the baseline (always-predict-majority), and the gain.",
  query: JSON.stringify(
    {
      testSource: { from: "invoices", where: { customer_id: "CUST-0000" }, limit: 50 },
      evaluate: {
        from: "invoices",
        where: { customer_id: "CUST-0000", vendor: { $get: "vendor" }, amount: { $get: "amount" } },
        predict: "gl_code",
      },
    },
    null,
    2,
  ),
  links: [
    { label: "API reference: _evaluate", url: "https://aito.ai/docs/api/#post-api-v1-evaluate" },
  ],
  flow_steps: [
    { n: 1, produces: "Held-out test sample per task", call: "testSource: { from, where, limit }" },
    { n: 2, produces: "Each task's accuracy", call: "_evaluate { evaluate: { predict, where: { ...features } } }" },
    { n: 3, produces: "Baseline accuracy", call: "Same _evaluate response: baseAccuracy = always-majority" },
    { n: 4, produces: "geomMeanP (calibrated confidence)", call: "Same _evaluate response: geomMeanP" },
  ],
};

interface Evaluation {
  task: string;
  context: string;
  operator: string;
  accuracy: number;
  baseAccuracy: number;
  accuracyGain: number;
  testSamples: number;
  geomMeanP: number;
  meanRank?: number;
  error?: string;
}

interface EvaluationsResponse {
  evaluations: Evaluation[];
}

function badgeClass(gain: number): string {
  if (gain >= 20) return "badge-green";
  if (gain >= 5) return "badge-gold";
  if (gain >= -2) return "badge-amber";
  return "badge-red";
}

export default function EvaluationsPage() {
  const { customerId } = useCustomer();
  const [data, setData] = useState<EvaluationsResponse | null>(null);
  const [live, setLive] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    setData(null);
    setLive(false);
    setError(null);
    apiFetch<EvaluationsResponse>(`/api/quality/evaluations?customer_id=${customerId}`)
      .then((d) => { setData(d); setLive(true); })
      .catch((e) => setError(e));
  }, [customerId]);

  return (
    <>
      <Nav />
      <div className="main">
        <TopBar
          breadcrumb="Quality"
          title="Evaluations Matrix"
          subtitle={data ? `${data.evaluations.length} prediction tasks evaluated via Aito _evaluate` : error ? "Backend not reachable" : "Running cross-validation..."}
          live={live}
        />
        <div className="content">
          <div style={{ background: "var(--surface2)", border: "1px solid var(--border2)", borderLeft: "3px solid var(--gold-mid)", borderRadius: 4, padding: "12px 16px", marginBottom: 16, fontSize: 12, color: "var(--text2)", lineHeight: 1.6 }}>
            <strong style={{ color: "var(--gold-dark)", marginRight: 6 }}>What this is.</strong>
            Each row is the answer to "if you held out a sample of this customer's
            history and asked Aito to predict it, how often would Aito be right?".
            <strong> Accuracy</strong> is the share of held-out predictions Aito got
            right; <strong>baseline</strong> is what an always-predict-majority
            classifier would get; <strong>gain</strong> is the difference; <strong>geomP </strong>
            is the geometric mean of Aito's predicted probability for the correct
            answer (higher = more confident calibration).
          </div>

          {error && <ErrorState error={error} />}

          {data && (
            <div className="card">
              <div className="card-header">
                <span className="card-title">Per-task evaluation results</span>
                <span className="card-hint">Each task runs in parallel · cached 10 min</span>
              </div>
              <table className="table" style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th>Task</th>
                    <th>Operator</th>
                    <th style={{ textAlign: "right" }}>Accuracy</th>
                    <th style={{ textAlign: "right" }}>Baseline</th>
                    <th style={{ textAlign: "right" }}>Gain</th>
                    <th style={{ textAlign: "right" }}>Samples</th>
                    <th style={{ textAlign: "right" }}>geomP</th>
                  </tr>
                </thead>
                <tbody>
                  {data.evaluations.map((e) => (
                    <tr key={e.task}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{e.task}</div>
                        <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 2 }}>{e.context}</div>
                      </td>
                      <td className="mono" style={{ fontSize: 11, color: "var(--gold-dark)" }}>{e.operator}</td>
                      {e.error ? (
                        <td colSpan={5} style={{ color: "var(--red)", fontSize: 11 }}>error: {e.error}</td>
                      ) : (
                        <>
                          <td className="mono" style={{ textAlign: "right", fontWeight: 600 }}>{e.accuracy}%</td>
                          <td className="mono" style={{ textAlign: "right", color: "var(--text3)" }}>{e.baseAccuracy}%</td>
                          <td className="mono" style={{ textAlign: "right" }}>
                            <span className={`badge ${badgeClass(e.accuracyGain)}`}>
                              {e.accuracyGain >= 0 ? "+" : ""}{e.accuracyGain}pp
                            </span>
                          </td>
                          <td className="mono" style={{ textAlign: "right", color: "var(--text3)" }}>{e.testSamples}</td>
                          <td className="mono" style={{ textAlign: "right", color: "var(--text3)" }}>{e.geomMeanP.toFixed(3)}</td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {!data && !error && (
            <div style={{ padding: 32, textAlign: "center", color: "var(--text3)", fontSize: 13 }}>
              Running 4 cross-validations in parallel against Aito… this takes 15–30s on first load.
            </div>
          )}

          {data && (
            <div style={{ background: "var(--surface)", border: "1px solid var(--border2)", borderRadius: 6, padding: "16px 20px", marginTop: 12, fontSize: 12, color: "var(--text2)", lineHeight: 1.7 }}>
              <strong style={{ color: "var(--text)" }}>How to read these numbers honestly:</strong>
              <ul style={{ margin: "8px 0 0 18px", padding: 0 }}>
                <li>
                  <strong>GL code</strong> and <strong>Approver</strong> are tasks where
                  Aito should beat the baseline by a wide margin — these are the headline
                  numbers an auditor cares about.
                </li>
                <li>
                  <strong>Bank-txn match</strong> evaluates whether Aito can recover the
                  vendor name from the bank description and amount. High accuracy = the
                  payment-matching feature is reliable on this customer's data.
                </li>
                <li>
                  <strong>Help click</strong> classification accuracy hovers near baseline
                  by design — most impressions don't lead to clicks. The signal is
                  captured by <strong>geomP</strong>: the same model produces useful
                  rankings via <code>_recommend</code> even when point accuracy is at
                  baseline.
                </li>
                <li>
                  <strong>Cold-start customers</strong> (small invoice count, like CUST-0254)
                  honestly show low accuracy here. That's working as intended — Aito
                  reports uncertainty rather than confident wrong answers.
                </li>
              </ul>
            </div>
          )}
        </div>
      </div>
      <AitoPanel config={PANEL} />
    </>
  );
}
