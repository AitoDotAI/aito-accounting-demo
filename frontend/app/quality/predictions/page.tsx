"use client";

import { useState, useEffect, useMemo, Fragment } from "react";
import Nav from "@/components/shell/Nav";
import { useCustomer } from "@/lib/customer-context";
import TopBar from "@/components/shell/TopBar";
import AitoPanel from "@/components/shell/AitoPanel";
import ErrorState from "@/components/shell/ErrorState";
import { apiFetch, fmtAmount } from "@/lib/api";
import type { AitoPanelConfig } from "@/lib/types";

const PANEL: AitoPanelConfig = {
  operation: "_evaluate (with cases)",
  stats: [
    { value: "_evaluate", label: "Operator" },
    { value: "Live", label: "Predictions" },
    { value: "$invoices", label: "Records" },
    { value: "Indexed", label: "Model" },
  ],
  description:
    'Per-domain evaluation using Aito\'s <code style="font-size:11px;color:var(--aito-accent)">_evaluate</code> with <code>select: [..., "cases"]</code>. ' +
    "Pick a domain, a target field to predict, and the input features to condition on. KPIs come from the aggregate response; the cases table shows individual predictions vs. ground truth.",
  query: JSON.stringify(
    {
      testSource: { from: "invoices", where: { customer_id: "CUST-0000" }, limit: 100 },
      evaluate: { from: "invoices", where: { customer_id: "CUST-0000", vendor: { $get: "vendor" }, amount: { $get: "amount" } }, predict: "gl_code" },
      select: ["accuracy", "meanRank", "testSamples", "cases"],
    },
    null, 2,
  ),
  links: [
    { label: "API reference: _evaluate", url: "https://aito.ai/docs/api/#post-api-v1-evaluate" },
    { label: "aito-demo evaluate.js", url: "https://github.com/AitoDotAI/aito-demo/blob/main/src/11-evaluate.js" },
  ],
};

interface DomainField { field: string; label: string; default?: boolean; }
interface DisplayColumn { field: string; label: string; mono?: boolean; format?: string; truncate?: boolean; }
interface Domain {
  key: string;
  label: string;
  table: string;
  predict_targets: { field: string; label: string }[];
  input_fields: DomainField[];
  display_columns: DisplayColumn[];
}
interface DomainsResponse { domains: Domain[]; }

interface KPIs {
  accuracy_pct: number;
  base_accuracy_pct: number;
  accuracy_gain_pct: number;
  mean_rank: number;
  geom_mean_p: number;
  test_samples: number;
  train_samples: number;
  correct_predictions: number;
  error_rate_pct: number;
}
interface Case {
  row_id: string;
  row: Record<string, any>;
  actual: any;
  predicted: any;
  confidence: number;
  correct: boolean;
}
interface EvalResponse {
  kpis?: KPIs;
  cases?: Case[];
  meta?: { domain: string; domain_label: string; predict: string; input_fields: string[]; query: any; display_columns: DisplayColumn[]; id_field: string };
  error?: string;
}

function fmtCell(value: any, fmt?: string, truncate?: boolean): string {
  if (value == null) return "—";
  if (fmt === "money" && typeof value === "number") return fmtAmount(value);
  const s = String(value);
  return truncate && s.length > 18 ? s.slice(0, 15) + "..." : s;
}

export default function PredictionQualityPage() {
  const { customerId } = useCustomer();
  const [catalog, setCatalog] = useState<Domain[]>([]);
  const [domainKey, setDomainKey] = useState<string>("invoices");
  const [predict, setPredict] = useState<string>("gl_code");
  const [inputs, setInputs] = useState<Set<string>>(new Set(["vendor", "amount", "category"]));
  const [limit, setLimit] = useState<number>(100);
  const [data, setData] = useState<EvalResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const domain = useMemo(() => catalog.find((d) => d.key === domainKey), [catalog, domainKey]);

  // Load catalog once
  useEffect(() => {
    apiFetch<DomainsResponse>("/api/quality/domains").then((r) => setCatalog(r.domains));
  }, []);

  // Reset predict + inputs when domain changes
  useEffect(() => {
    if (!domain) return;
    setPredict(domain.predict_targets[0]?.field || "");
    const defaults = new Set(domain.input_fields.filter((f) => f.default).map((f) => f.field));
    setInputs(defaults);
  }, [domain]);

  // Run evaluation when (customerId, domain, predict, inputs, limit) changes
  useEffect(() => {
    if (!domain || !predict || inputs.size === 0) return;
    setLoading(true);
    setData(null);
    const fieldList = Array.from(inputs).join(",");
    apiFetch<EvalResponse>(
      `/api/quality/evaluate?customer_id=${encodeURIComponent(customerId)}&domain=${domainKey}&predict=${encodeURIComponent(predict)}&input_fields=${encodeURIComponent(fieldList)}&limit=${limit}`,
    )
      .then(setData)
      .catch((e) => setData({ error: String(e) }))
      .finally(() => setLoading(false));
  }, [customerId, domainKey, predict, inputs, limit, domain]);

  const toggleInput = (field: string) => {
    setInputs((prev) => {
      const next = new Set(prev);
      if (next.has(field)) next.delete(field);
      else next.add(field);
      return next;
    });
  };

  const k = data?.kpis;
  const cases = data?.cases ?? [];
  const cols = data?.meta?.display_columns ?? domain?.display_columns ?? [];

  return (
    <>
      <Nav />
      <div className="main">
        <TopBar
          breadcrumb="Quality"
          title="Prediction Quality"
          subtitle={
            data?.error ? "Backend not reachable" :
            loading ? "Running _evaluate…" :
            k ? `${k.test_samples} test cases · ${k.accuracy_pct}% accuracy` :
            "Pick a domain, predict target and input features"
          }
          live={!!k}
        />
        <div className="content">
          {/* Domain selector pills */}
          <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
            {catalog.map((d) => {
              const active = d.key === domainKey;
              return (
                <button
                  key={d.key}
                  onClick={() => setDomainKey(d.key)}
                  style={{
                    padding: "8px 18px",
                    fontSize: 13,
                    fontWeight: 600,
                    borderRadius: 6,
                    border: "1px solid " + (active ? "var(--gold-dark)" : "var(--border)"),
                    background: active ? "var(--gold-dark)" : "var(--surface)",
                    color: active ? "#f5e8c0" : "var(--text2)",
                    cursor: "pointer",
                    fontFamily: "inherit",
                  }}
                >
                  {d.label}
                </button>
              );
            })}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "minmax(260px, 320px) 1fr", gap: 16 }}>
            {/* LEFT: Configurator */}
            <div className="card" style={{ alignSelf: "start" }}>
              <div className="card-header">
                <span className="card-title">Evaluation configuration</span>
              </div>
              <div style={{ padding: 16 }}>
                {/* Predict target */}
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", marginBottom: 6 }}>
                    Prediction target
                  </div>
                  <select
                    value={predict}
                    onChange={(e) => setPredict(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "8px 10px",
                      fontSize: 13,
                      border: "1px solid var(--border)",
                      borderRadius: 6,
                      background: "var(--surface2)",
                      color: "var(--text)",
                      fontFamily: "inherit",
                    }}
                  >
                    {domain?.predict_targets.map((t) => (
                      <option key={t.field} value={t.field}>{t.label} — {t.field}</option>
                    ))}
                  </select>
                  <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 6, lineHeight: 1.5 }}>
                    Field whose value Aito predicts on the held-out test set.
                  </div>
                </div>

                {/* Test sample size */}
                <div style={{ marginBottom: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                    <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px" }}>
                      Test set size
                    </span>
                    <span style={{ fontSize: 11, fontFamily: "'IBM Plex Mono', monospace", color: "var(--gold-dark)" }}>{limit}</span>
                  </div>
                  <input
                    type="range"
                    min={20}
                    max={300}
                    step={10}
                    value={limit}
                    onChange={(e) => setLimit(parseInt(e.target.value, 10))}
                    style={{ width: "100%" }}
                  />
                  <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 4, lineHeight: 1.5 }}>
                    Capped at 300 to keep latency bounded. Larger = more stable accuracy estimate, slower call.
                  </div>
                </div>

                {/* Input fields */}
                <div>
                  <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", marginBottom: 6 }}>
                    Input features
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    {domain?.input_fields.filter((f) => f.field !== predict).map((f) => (
                      <label key={f.field} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, color: "var(--text2)", padding: "4px 0", cursor: "pointer" }}>
                        <input
                          type="checkbox"
                          checked={inputs.has(f.field)}
                          onChange={() => toggleInput(f.field)}
                        />
                        <span>{f.label}</span>
                        <code style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, color: "var(--text3)" }}>{f.field}</code>
                      </label>
                    ))}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 6, lineHeight: 1.5 }}>
                    These map to <code style={{ fontFamily: "'IBM Plex Mono', monospace" }}>{`{ $get: "fieldname" }`}</code> bindings in the where clause.
                  </div>
                </div>
              </div>
            </div>

            {/* RIGHT: KPIs + cases */}
            <div>
              {/* KPIs */}
              <div className="card" style={{ marginBottom: 12 }}>
                <div className="card-header">
                  <span className="card-title">Model performance</span>
                  <span className="card-hint">From <code>_evaluate</code> aggregate</span>
                </div>
                <div style={{ padding: 16, display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16 }}>
                  <KPI label="Accuracy" value={k ? `${k.accuracy_pct}%` : "—"} sub={k ? `vs ${k.base_accuracy_pct}% base` : ""} highlight />
                  <KPI label="Mean rank" value={k ? k.mean_rank.toFixed(2) : "—"} sub="lower = better" />
                  <KPI label="Geom mean p" value={k ? k.geom_mean_p.toFixed(3) : "—"} sub="calibrated conf." />
                  <KPI label="Gain" value={k ? `${k.accuracy_gain_pct >= 0 ? "+" : ""}${k.accuracy_gain_pct}pp` : "—"} sub="vs baseline" />
                </div>
                <div style={{ padding: "0 16px 16px", display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
                  <KPI label="Test samples" value={k ? String(k.test_samples) : "—"} />
                  <KPI label="Train samples" value={k ? String(k.train_samples) : "—"} />
                  <KPI label="Correct" value={k ? `${k.correct_predictions} / ${k.test_samples}` : "—"} />
                </div>
              </div>

              {data?.error && <ErrorState />}

              {/* Cases table */}
              <div className="card">
                <div className="card-header">
                  <span className="card-title">Evaluation cases</span>
                  <span className="card-hint">First {cases.length} of {k?.test_samples ?? 0} · green=correct, red=wrong</span>
                </div>
                {loading && (
                  <div style={{ padding: 24, textAlign: "center", color: "var(--text3)", fontSize: 13 }}>Running _evaluate…</div>
                )}
                {!loading && cases.length === 0 && !data?.error && (
                  <div style={{ padding: 24, textAlign: "center", color: "var(--text3)", fontSize: 13 }}>
                    No cases returned. Pick at least one input field.
                  </div>
                )}
                {cases.length > 0 && (
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                    <thead>
                      <tr>
                        <th style={{ width: 8, padding: "8px 0", borderBottom: "1px solid var(--border2)" }}></th>
                        {cols.map((col) => (
                          <th key={col.field} style={{ textAlign: "left", padding: "8px 12px", fontSize: 11, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", fontWeight: 600, borderBottom: "1px solid var(--border2)" }}>
                            {col.label}
                          </th>
                        ))}
                        <th style={{ textAlign: "left", padding: "8px 12px", fontSize: 11, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", fontWeight: 600, borderBottom: "1px solid var(--border2)" }}>Actual</th>
                        <th style={{ textAlign: "left", padding: "8px 12px", fontSize: 11, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", fontWeight: 600, borderBottom: "1px solid var(--border2)" }}>Predicted</th>
                        <th style={{ textAlign: "right", padding: "8px 12px", fontSize: 11, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", fontWeight: 600, borderBottom: "1px solid var(--border2)" }}>Conf.</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cases.map((c, i) => (
                        <tr key={i} style={{ background: c.correct ? undefined : "rgba(220, 53, 69, 0.04)", borderBottom: "1px solid var(--border2)" }}>
                          <td style={{ width: 8, padding: 0, background: c.correct ? "var(--green)" : "var(--red)" }}></td>
                          {cols.map((col) => (
                            <td key={col.field} className={col.mono ? "mono" : undefined} style={{ padding: "8px 12px" }}>
                              {fmtCell(c.row[col.field], col.format, col.truncate)}
                            </td>
                          ))}
                          <td className="mono" style={{ padding: "8px 12px", fontWeight: 600 }}>{String(c.actual ?? "—")}</td>
                          <td className="mono" style={{ padding: "8px 12px", color: c.correct ? "var(--green)" : "var(--red)", fontWeight: 600 }}>
                            {String(c.predicted ?? "—")}
                          </td>
                          <td className="mono" style={{ padding: "8px 12px", textAlign: "right", color: "var(--text3)" }}>
                            {c.confidence ? c.confidence.toFixed(2) : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
      <AitoPanel config={PANEL} lastQuery={data?.meta?.query} />
    </>
  );
}

function KPI({ label, value, sub, highlight }: { label: string; value: string; sub?: string; highlight?: boolean }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", fontWeight: 600 }}>{label}</div>
      <div style={{ fontSize: highlight ? 26 : 22, fontFamily: "'IBM Plex Mono', monospace", fontWeight: 600, color: highlight ? "var(--gold-dark)" : "var(--text)", marginTop: 4 }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: "var(--text3)", marginTop: 2 }}>{sub}</div>}
    </div>
  );
}
