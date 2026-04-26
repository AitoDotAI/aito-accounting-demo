"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Nav from "@/components/shell/Nav";
import TopBar from "@/components/shell/TopBar";
import AitoPanel from "@/components/shell/AitoPanel";
import PredictedField from "@/components/prediction/PredictedField";
import { useCustomer } from "@/lib/customer-context";
import { apiFetch } from "@/lib/api";
import type { AitoPanelConfig } from "@/lib/types";

const PANEL_CONFIG: AitoPanelConfig = {
  operation: "_predict (multi-field)",
  stats: [
    { value: "0.95", label: "Avg confidence" },
    { value: "6", label: "Fields" },
    { value: "$invoices", label: "Records" },
    { value: "Zero", label: "Training" },
  ],
  description:
    'Type in any field \u2014 all other fields predict automatically via <code style="font-size:11px;color:var(--aito-accent)">_predict</code>. ' +
    "Each prediction shows which input features drove it via <code style=\"font-size:11px;color:var(--aito-accent)\">$why</code>.",
  query: JSON.stringify(
    { from: "invoices", where: { vendor: "Kesko Oyj" }, predict: "gl_code", select: ["$p", "feature", "$why"] },
    null,
    2,
  ),
  links: [
    { label: "API reference: _predict", url: "https://aito.ai/docs/api/#post-api-v1-predict" },
    { label: "Smart form fill docs", url: "https://aito.ai/docs" },
  ],
};

interface FieldPrediction {
  field: string;
  label: string;
  value: string | null;
  raw_value: string | null;
  confidence: number;
  predicted: boolean;
  alternatives?: { value: string; display: string; confidence: number; why?: { field: string; value: string; lift: number }[] }[];
}

interface PredictResponse {
  where: Record<string, string | number>;
  fields: FieldPrediction[];
  predicted_count: number;
  avg_confidence: number;
}

export default function FormFillPage() {
  const { customerId } = useCustomer();
  const [userValues, setUserValues] = useState<Record<string, string>>({});
  const [predictions, setPredictions] = useState<FieldPrediction[]>([]);
  const [loading, setLoading] = useState(false);
  const [live, setLive] = useState(false);
  const [lastQuery, setLastQuery] = useState<object | null>(null);
  const [vendors, setVendors] = useState<string[]>([]);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    apiFetch<{ vendors: string[] }>(`/api/formfill/vendors?customer_id=${customerId}`)
      .then((d) => setVendors(d.vendors))
      .catch(() => setVendors(["Kesko Oyj", "Telia Finland", "Fazer Bakeries", "SOK Corporation"]));
  }, []);

  const fetchPredictions = useCallback(async (values: Record<string, string>) => {
    const where: Record<string, string | number> = {};
    for (const [k, v] of Object.entries(values)) {
      if (!v) continue;
      if (k === "amount") {
        const num = parseFloat(v);
        if (!isNaN(num)) where[k] = num;
      } else {
        where[k] = v;
      }
    }

    if (Object.keys(where).length === 0) {
      setPredictions([]);
      setLastQuery(null);
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setLastQuery({ from: "invoices", where, predict: "remaining fields", select: ["$p", "feature", "$why"] });

    try {
      const data = await apiFetch<PredictResponse>("/api/formfill/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({...where, customer_id: customerId}),
        signal: controller.signal,
      });
      setPredictions(data.fields);
      setLive(true);
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
    } finally {
      setLoading(false);
    }
  }, []);

  const handleChange = useCallback((field: string, value: string) => {
    setUserValues((prev) => {
      const next = { ...prev, [field]: value };
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => fetchPredictions(next), 300);
      return next;
    });
  }, [fetchPredictions]);

  const handleVendorSelect = useCallback((vendor: string) => {
    const next = { ...userValues, vendor };
    setUserValues(next);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    fetchPredictions(next);
  }, [userValues, fetchPredictions]);

  const handleClear = useCallback(() => {
    setUserValues({});
    setPredictions([]);
    setLastQuery(null);
  }, []);

  const getPrediction = (fieldName: string): FieldPrediction | undefined =>
    predictions.find((p) => p.field === fieldName);

  const predictedCount = predictions.filter((p) => p.predicted).length;
  const avgConf = predictedCount > 0
    ? predictions.filter((p) => p.predicted).reduce((sum, p) => sum + p.confidence, 0) / predictedCount
    : 0;

  return (
    <>
      <Nav />
      <div className="main">
        <TopBar
          breadcrumb="Payables"
          title="Smart Form Fill"
          subtitle={loading ? "Predicting..." : predictedCount > 0 ? `${predictedCount} fields predicted \u00B7 avg ${(avgConf * 100).toFixed(0)}% confidence` : "Type in any field to trigger predictions"}
          live={live}
          actions={
            <button className="btn btn-outline" onClick={handleClear}>Clear</button>
          }
        />
        <div className="content">
          {predictedCount > 0 && (
            <div style={{ background: "var(--gold-light)", border: "1px solid #d8bc70", borderRadius: 8, padding: "10px 16px", fontSize: "12.5px", color: "var(--gold-dark)", display: "flex", alignItems: "center", gap: 8 }}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.3"/><path d="M7 4v3.5L9 9" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>
              Aito predicted {predictedCount} fields. Click <strong style={{ margin: "0 2px" }}>?</strong> to see why each prediction was made.
            </div>
          )}

          <div className="form-grid">
            <div className="form-section">
              <div className="form-section-title">Invoice details</div>

              <div className="field-group">
                <div className="field-label">Vendor name</div>
                <div style={{ display: "flex", gap: 8 }}>
                  <input
                    className="field-input"
                    value={userValues.vendor || ""}
                    onChange={(e) => handleChange("vendor", e.target.value)}
                    placeholder="Type or select vendor"
                    style={{ flex: 1 }}
                  />
                  <select
                    className="field-input"
                    style={{ width: 140, cursor: "pointer" }}
                    value=""
                    onChange={(e) => e.target.value && handleVendorSelect(e.target.value)}
                  >
                    <option value="">Quick pick</option>
                    {vendors.map((v) => (
                      <option key={v} value={v}>{v}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="field-row">
                <div className="field-group">
                  <div className="field-label">Amount excl. VAT</div>
                  <input
                    className="field-input"
                    value={userValues.amount || ""}
                    onChange={(e) => handleChange("amount", e.target.value)}
                    placeholder="e.g. 4220.00"
                    type="number"
                    step="0.01"
                  />
                </div>
                <div className="field-group">
                  <div className="field-label">Category</div>
                  <select
                    className="field-input"
                    value={userValues.category || ""}
                    onChange={(e) => handleChange("category", e.target.value)}
                    style={{ cursor: "pointer" }}
                  >
                    <option value="">-- Optional --</option>
                    <option value="telecom">Telecom</option>
                    <option value="supplies">Supplies</option>
                    <option value="food_bev">Food &amp; Beverage</option>
                    <option value="office">Office</option>
                    <option value="it_equipment">IT Equipment</option>
                    <option value="facilities">Facilities</option>
                    <option value="maintenance">Maintenance</option>
                    <option value="software">Software</option>
                    <option value="cloud">Cloud</option>
                  </select>
                </div>
              </div>

              <div className="field-row">
                <div className="field-group">
                  <div className="field-label">Invoice date</div>
                  <input className="field-input" defaultValue="2026-04-18" readOnly />
                </div>
                <PredictedField
                  label="Due terms"
                  fieldName="due_days"
                  value={getPrediction("due_days")?.value || ""}
                  predicted={getPrediction("due_days")?.predicted || false}
                  confidence={getPrediction("due_days")?.confidence}
                  whyFactors={getPrediction("due_days")?.alternatives?.[0]?.why}
                  onChange={handleChange}
                />
              </div>

              <PredictedField
                label="VAT %"
                fieldName="vat_pct"
                value={getPrediction("vat_pct")?.value || ""}
                predicted={getPrediction("vat_pct")?.predicted || false}
                confidence={getPrediction("vat_pct")?.confidence}
                whyFactors={getPrediction("vat_pct")?.alternatives?.[0]?.why}
                onChange={handleChange}
              />
            </div>

            <div className="form-section">
              <div className="form-section-title">Routing &amp; classification</div>

              <PredictedField
                label="GL Account"
                fieldName="gl_code"
                value={getPrediction("gl_code")?.value || ""}
                predicted={getPrediction("gl_code")?.predicted || false}
                confidence={getPrediction("gl_code")?.confidence}
                whyFactors={getPrediction("gl_code")?.alternatives?.[0]?.why}
                onChange={handleChange}
              />
              <PredictedField
                label="Cost centre"
                fieldName="cost_centre"
                value={getPrediction("cost_centre")?.value || ""}
                predicted={getPrediction("cost_centre")?.predicted || false}
                confidence={getPrediction("cost_centre")?.confidence}
                whyFactors={getPrediction("cost_centre")?.alternatives?.[0]?.why}
                onChange={handleChange}
              />
              <PredictedField
                label="Approver"
                fieldName="approver"
                value={getPrediction("approver")?.value || ""}
                predicted={getPrediction("approver")?.predicted || false}
                confidence={getPrediction("approver")?.confidence}
                whyFactors={getPrediction("approver")?.alternatives?.[0]?.why}
                onChange={handleChange}
              />
              <PredictedField
                label="Payment method"
                fieldName="payment_method"
                value={getPrediction("payment_method")?.value || ""}
                predicted={getPrediction("payment_method")?.predicted || false}
                confidence={getPrediction("payment_method")?.confidence}
                whyFactors={getPrediction("payment_method")?.alternatives?.[0]?.why}
                onChange={handleChange}
              />
              <div className="field-group">
                <div className="field-label">Project code</div>
                <input className="field-input" placeholder="Optional" />
              </div>
            </div>
          </div>
        </div>
      </div>
      <AitoPanel config={PANEL_CONFIG} lastQuery={lastQuery} />
    </>
  );
}
