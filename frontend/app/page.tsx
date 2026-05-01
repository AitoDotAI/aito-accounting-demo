"use client";

import { useEffect, useMemo, useState } from "react";
import Nav from "@/components/shell/Nav";
import TopBar from "@/components/shell/TopBar";
import AitoPanel from "@/components/shell/AitoPanel";
import { apiFetch } from "@/lib/api";
import { glLabel } from "@/lib/gl-labels";
import type { AitoPanelConfig } from "@/lib/types";

interface SharedTenant {
  customer_id: string;
  gl_code: string;
  n: number;
}

interface SharedVendor {
  vendor: string;
  tenant_count: number;
  distinct_gls: number;
  tenants: SharedTenant[];
}

interface CustomerLite {
  customer_id: string;
  name: string;
  size_tier: string;
  invoice_count: number;
}

interface Template {
  vendor: string;
  match_count: number;
  total_history: number;
  confidence: number;
  fields: {
    gl_code: string;
    gl_label?: string;
    approver?: string;
    cost_centre?: string;
    category?: string;
  };
  error?: string;
}

const PANEL_CONFIG: AitoPanelConfig = {
  operation: "_predict",
  stats: [
    { value: "_predict", label: "Operation" },
    { value: "255", label: "Tenants" },
    { value: "1", label: "Aito instance" },
    { value: "0", label: "Models / tenant" },
  ],
  description:
    'One Aito instance, 255 tenants, no per-tenant model files. Each ' +
    '<code style="font-size:11px;color:var(--aito-accent)">_predict</code> carries ' +
    '<code style="font-size:11px;color:var(--aito-accent)">customer_id</code> in the ' +
    'where clause; tenants\' histories condition independently. Cold-start is honest, ' +
    'cross-tenant leakage is structurally impossible.',
  query: JSON.stringify(
    {
      from: "invoices",
      where: { customer_id: "CUST-0000", vendor: "Inside Restaurant Service Oy" },
      predict: "gl_code",
      select: ["$p", "feature", "$why"],
    },
    null,
    2,
  ),
  links: [
    { label: "ADR-0012: single-table multi-tenancy", url: "https://github.com/AitoDotAI/aito-accounting-demo/blob/main/docs/adr/0012-single-table-multitenancy.md" },
    { label: "Guide: multi-tenancy via where clause", url: "https://aito.ai/docs/api/" },
  ],
};

// Curated tenants to show side-by-side: top by invoice count, picked for
// industry contrast. The endpoint returns more — we cap to 4 for the
// 4-card layout to stay readable on a 1024px viewport.
const MAX_TENANTS_VISIBLE = 4;

const SIZE_LABELS: Record<string, string> = {
  enterprise: "Enterprise",
  large: "Large",
  mid: "Mid-market",
  small: "Small",
  micro: "Micro",
};

function tenantHeadline(c: CustomerLite | undefined, fallbackId: string) {
  if (!c) return fallbackId;
  return c.name || fallbackId;
}

function tenantSize(c: CustomerLite | undefined) {
  if (!c) return "";
  const tier = SIZE_LABELS[c.size_tier] || c.size_tier;
  return `${tier} · ${c.invoice_count.toLocaleString()} invoices`;
}

export default function Home() {
  const [vendors, setVendors] = useState<SharedVendor[]>([]);
  const [customers, setCustomers] = useState<CustomerLite[]>([]);
  const [vendorIdx, setVendorIdx] = useState(0);
  const [predictions, setPredictions] = useState<Record<string, Template | null>>({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    apiFetch<{ vendors: SharedVendor[] }>("/api/multitenancy/shared_vendors?limit=8")
      .then((d) => setVendors(d.vendors ?? []))
      .catch(() => setVendors([]));
    apiFetch<{ customers: CustomerLite[] }>("/api/customers")
      .then((d) => setCustomers(d.customers ?? []))
      .catch(() => setCustomers([]));
  }, []);

  const selectedVendor = vendors[vendorIdx];
  const visibleTenants = useMemo(() => {
    if (!selectedVendor) return [];
    return selectedVendor.tenants.slice(0, MAX_TENANTS_VISIBLE);
  }, [selectedVendor]);

  const customerById = useMemo(() => {
    const m: Record<string, CustomerLite> = {};
    for (const c of customers) m[c.customer_id] = c;
    return m;
  }, [customers]);

  // When the vendor changes, fan out predictions across the visible
  // tenants in parallel. Cleared first so stale cards don't flicker.
  useEffect(() => {
    if (!selectedVendor) return;
    let cancelled = false;
    setPredictions({});
    setLoading(true);
    const calls = visibleTenants.map((t) =>
      apiFetch<Template>(
        `/api/formfill/template?customer_id=${encodeURIComponent(t.customer_id)}&vendor=${encodeURIComponent(selectedVendor.vendor)}`,
      )
        .then((tpl) => [t.customer_id, tpl] as const)
        .catch(() => [t.customer_id, null] as const),
    );
    Promise.all(calls).then((rows) => {
      if (cancelled) return;
      const next: Record<string, Template | null> = {};
      for (const [id, tpl] of rows) next[id] = tpl;
      setPredictions(next);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [selectedVendor, visibleTenants]);

  const distinctGlsAcrossVisible = useMemo(() => {
    const set = new Set<string>();
    for (const t of visibleTenants) {
      const tpl = predictions[t.customer_id];
      if (tpl?.fields?.gl_code) set.add(tpl.fields.gl_code);
    }
    return set.size;
  }, [predictions, visibleTenants]);

  return (
    <>
      <Nav />
      <div className="main">
        <TopBar
          breadcrumb="Multi-tenancy"
          title="Same vendor. Different tenants. Different predictions."
          subtitle="One Aito instance · 255 tenants · zero per-tenant models"
          live
        />
        <div className="content">
          {/* Vendor picker */}
          <div className="card" style={{ padding: "16px 20px" }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", marginBottom: 6 }}>
              Pick a shared vendor
            </div>
            <div style={{ fontSize: 12, color: "var(--text3)", marginBottom: 12, lineHeight: 1.55 }}>
              These vendors appear in {selectedVendor?.tenant_count ?? "—"}+ tenants&apos; ledgers.
              Each tenant routes the same vendor to its own GL —
              <strong style={{ color: "var(--text2)" }}> {distinctGlsAcrossVisible || "—"} different GL codes</strong> across the {visibleTenants.length || "—"} tenants shown.
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {vendors.map((v, i) => (
                <button
                  key={v.vendor}
                  onClick={() => setVendorIdx(i)}
                  style={{
                    padding: "7px 13px",
                    borderRadius: 18,
                    border: i === vendorIdx ? "1px solid var(--gold-dark)" : "1px solid var(--border)",
                    background: i === vendorIdx ? "var(--gold-light)" : "var(--surface)",
                    color: i === vendorIdx ? "var(--gold-dark)" : "var(--text2)",
                    fontSize: 12,
                    fontFamily: "inherit",
                    cursor: "pointer",
                    fontWeight: i === vendorIdx ? 600 : 500,
                  }}
                  title={`${v.tenant_count} tenants · ${v.distinct_gls} distinct GLs`}
                >
                  {v.vendor}
                  <span style={{
                    marginLeft: 6,
                    fontSize: 10,
                    color: i === vendorIdx ? "var(--gold-dark)" : "var(--text3)",
                    fontFamily: "'IBM Plex Mono', monospace",
                  }}>
                    {v.distinct_gls} GLs
                  </span>
                </button>
              ))}
              {vendors.length === 0 && (
                <div className="skeleton" style={{ width: 360, height: 28, borderRadius: 14 }} />
              )}
            </div>
          </div>

          {/* Tenant prediction cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14 }}>
            {visibleTenants.map((t) => {
              const tpl = predictions[t.customer_id];
              const c = customerById[t.customer_id];
              const ready = tpl !== undefined && !loading;
              const error = ready && (tpl === null || tpl?.error);
              return (
                <div
                  key={t.customer_id}
                  className="card"
                  style={{ padding: 0, display: "flex", flexDirection: "column" }}
                >
                  <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border2)", background: "var(--surface2)" }}>
                    <div style={{ fontSize: 10, fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".5px", fontFamily: "'IBM Plex Mono', monospace" }}>
                      {t.customer_id}
                    </div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)", marginTop: 2 }}>
                      {tenantHeadline(c, t.customer_id)}
                    </div>
                    <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 2 }}>
                      {tenantSize(c)}
                    </div>
                  </div>

                  <div style={{ padding: "14px 16px", flex: 1 }}>
                    <div style={{ fontSize: 10, fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".5px", marginBottom: 6 }}>
                      Predicted GL code
                    </div>
                    {!ready && (
                      <div className="skeleton" style={{ width: 120, height: 26, borderRadius: 4 }} />
                    )}
                    {ready && error && (
                      <div style={{ fontSize: 12, color: "var(--text3)", padding: "6px 0" }}>
                        Not enough history for this vendor in this tenant.
                      </div>
                    )}
                    {ready && !error && tpl && (
                      <>
                        <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                          <span style={{ fontSize: 22, fontWeight: 600, fontFamily: "'IBM Plex Mono', monospace", color: "var(--gold-dark)" }}>
                            {tpl.fields.gl_code}
                          </span>
                          <span style={{ fontSize: 12, color: "var(--text2)" }}>
                            {tpl.fields.gl_label || glLabel(tpl.fields.gl_code)}
                          </span>
                        </div>
                        <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 6, lineHeight: 1.5 }}>
                          <span style={{ fontFamily: "'IBM Plex Mono', monospace", color: "var(--green)" }}>
                            {tpl.match_count}
                          </span>
                          {" of "}
                          <span style={{ fontFamily: "'IBM Plex Mono', monospace" }}>
                            {tpl.total_history}
                          </span>
                          {" prior invoices in this ledger routed identically"}
                        </div>

                        <div style={{ marginTop: 12, paddingTop: 10, borderTop: "1px dashed var(--border2)", display: "grid", gridTemplateColumns: "auto 1fr", gap: "5px 10px", fontSize: 11.5 }}>
                          {tpl.fields.approver && (
                            <>
                              <span style={{ color: "var(--text3)" }}>Approver</span>
                              <span style={{ color: "var(--text2)" }}>{tpl.fields.approver}</span>
                            </>
                          )}
                          {tpl.fields.cost_centre && (
                            <>
                              <span style={{ color: "var(--text3)" }}>Cost centre</span>
                              <span style={{ color: "var(--text2)", fontFamily: "'IBM Plex Mono', monospace" }}>{tpl.fields.cost_centre}</span>
                            </>
                          )}
                          {tpl.fields.category && (
                            <>
                              <span style={{ color: "var(--text3)" }}>Category</span>
                              <span style={{ color: "var(--text2)" }}>{tpl.fields.category}</span>
                            </>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
            {visibleTenants.length === 0 && [0, 1, 2, 3].map((i) => (
              <div key={i} className="card" style={{ padding: 16 }}>
                <div className="skeleton" style={{ width: "60%", height: 14, borderRadius: 3, marginBottom: 8 }} />
                <div className="skeleton" style={{ width: "80%", height: 11, borderRadius: 3, marginBottom: 12 }} />
                <div className="skeleton" style={{ width: 80, height: 24, borderRadius: 4 }} />
              </div>
            ))}
          </div>

          {/* Query proof block */}
          {selectedVendor && (
            <div className="card" style={{ padding: "16px 20px" }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", marginBottom: 8 }}>
                The query — identical except for <code style={{ fontFamily: "'IBM Plex Mono', monospace", color: "var(--gold-dark)" }}>customer_id</code>
              </div>
              <pre style={{
                background: "var(--surface2)",
                border: "1px solid var(--border2)",
                borderRadius: 6,
                padding: "12px 14px",
                fontSize: 11.5,
                lineHeight: 1.6,
                overflow: "auto",
                margin: 0,
                fontFamily: "'IBM Plex Mono', monospace",
                color: "var(--text2)",
              }}>
                <code>{`POST /_predict
{
  "from": "invoices",
  "where": {
    "customer_id": "<tenant>",          ← only this changes
    "vendor": "${selectedVendor.vendor}"
  },
  "predict": "gl_code",
  "select": ["$p", "feature", "$why"]
}`}</code>
              </pre>
              <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 10, lineHeight: 1.55 }}>
                Same Aito instance. Same schema. Same query shape. Each tenant&apos;s
                history conditions independently — no per-tenant model file, no
                training step, no batch rebuild when a tenant onboards.
              </div>
            </div>
          )}

          <div style={{ display: "flex", gap: 14, alignItems: "stretch", flexWrap: "wrap" }}>
            <a
              href="/formfill"
              className="card"
              style={{ padding: "14px 18px", flex: "1 1 280px", textDecoration: "none", color: "var(--text)", display: "block" }}
            >
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--gold-dark)", textTransform: "uppercase", letterSpacing: ".5px" }}>
                Try it on a fresh invoice →
              </div>
              <div style={{ fontSize: 13, color: "var(--text2)", marginTop: 4, lineHeight: 1.5 }}>
                Smart Form Fill: type any vendor, watch GL / approver / cost-centre /
                VAT predict in one round trip.
              </div>
            </a>
            <a
              href="/quality/predictions"
              className="card"
              style={{ padding: "14px 18px", flex: "1 1 280px", textDecoration: "none", color: "var(--text)", display: "block" }}
            >
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--gold-dark)", textTransform: "uppercase", letterSpacing: ".5px" }}>
                See the per-tenant accuracy →
              </div>
              <div style={{ fontSize: 13, color: "var(--text2)", marginTop: 4, lineHeight: 1.5 }}>
                Prediction Quality runs <code style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 11 }}>_evaluate</code> per
                tenant with held-out splits. Honest accuracy, including the small ones.
              </div>
            </a>
          </div>
        </div>
      </div>
      <AitoPanel config={PANEL_CONFIG} />
    </>
  );
}
