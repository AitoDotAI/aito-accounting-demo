"use client";

import { useEffect, useState } from "react";
import { useCustomer } from "@/lib/customer-context";
import { useTour } from "@/lib/tour-context";
import type { AitoPanelConfig, AitoPanelStat } from "@/lib/types";

interface AitoPanelProps {
  config: AitoPanelConfig;
  lastQuery?: object | null;
  lastResponseMs?: number | null;
}

const IconChevronRight = () => (
  <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true" width="12" height="12">
    <path d="M5.5 3l5 5-5 5L4 11.5 7.5 8 4 4.5z"/>
  </svg>
);

const IconChevronLeft = () => (
  <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true" width="12" height="12">
    <path d="M10.5 3l-5 5 5 5L12 11.5 8.5 8 12 4.5z"/>
  </svg>
);

// Resolve stats that reference live customer data via the special "$" prefix
function resolveStat(stat: AitoPanelStat, ctx: { invoices: number; employees: number }): AitoPanelStat {
  if (stat.value === "$invoices") return { ...stat, value: ctx.invoices.toLocaleString() };
  if (stat.value === "$employees") return { ...stat, value: ctx.employees.toLocaleString() };
  return stat;
}

const IconExternal = () => (
  <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
    <path d="M9 2v1.5h3.44L6.97 8.97l1.06 1.06L13.5 4.56V8H15V2H9zM3 4h5V2.5H3A1.5 1.5 0 001.5 4v9A1.5 1.5 0 003 14.5h9A1.5 1.5 0 0013.5 13V8H12v5H3V4z"/>
  </svg>
);

const IconBook = () => (
  <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
    <path d="M3 2.5A1.5 1.5 0 014.5 1H13v12H4.5a1 1 0 100 2H13v1H4.5A2.5 2.5 0 012 13.5v-11zM4.5 2.5v9.05A2.49 2.49 0 015 11.5h6.5v-9h-7z"/>
  </svg>
);

const IconCode = () => (
  <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
    <path d="M5.5 4.5L1 8l4.5 3.5 1-1.3L3 8l3.5-2.2-1-1.3zM10.5 4.5l-1 1.3L13 8l-3.5 2.2 1 1.3L15 8l-4.5-3.5z"/>
  </svg>
);

function linkIcon(label: string) {
  const l = label.toLowerCase();
  if (l.includes("schema") || l.includes("workbook")) return <IconBook />;
  if (l.includes("source") || l.includes("github")) return <IconCode />;
  return <IconExternal />;
}

export default function AitoPanel({ config, lastQuery, lastResponseMs }: AitoPanelProps) {
  const { currentCustomer, customers, customerId } = useCustomer();
  const { tourOn } = useTour();
  const [collapsed, setCollapsed] = useState(false);
  // `mobileOpen` controls the bottom-sheet on small screens. It is
  // independent of `collapsed` (desktop) so the two breakpoints don't
  // fight each other on resize.
  const [mobileOpen, setMobileOpen] = useState(false);
  useEffect(() => {
    const stored = typeof window !== "undefined" ? localStorage.getItem("aitoPanelCollapsed") : null;
    if (stored === "true") setCollapsed(true);
  }, []);
  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    try { localStorage.setItem("aitoPanelCollapsed", String(next)); } catch { /* noop */ }
  };
  const closeMobile = () => setMobileOpen(false);
  const totalInvoices = customers.reduce((sum, c) => sum + (c.invoice_count || 0), 0);
  const ctx = {
    invoices: currentCustomer?.invoice_count ?? totalInvoices,
    employees: currentCustomer?.employee_count ?? 0,
  };
  const stats = config.stats.map((s) => resolveStat(s, ctx));

  // Pages embed example queries with "CUST-0000" hardcoded so the
  // displayed JSON looks copyable. When a different customer is
  // selected, swap the literal so the example query reflects what's
  // actually being queried for the customer on screen.
  const exampleQuery = customerId && customerId !== "CUST-0000"
    ? config.query.replaceAll("\"CUST-0000\"", `"${customerId}"`)
    : config.query;

  return (
    <>
      <button
        className={`aito-panel-toggle${collapsed ? "" : " expanded"}`}
        onClick={toggle}
        aria-label={collapsed ? "Open Aito panel" : "Close Aito panel"}
        title={collapsed ? "Open Aito panel" : "Close Aito panel"}
      >
        {collapsed ? <IconChevronLeft /> : <IconChevronRight />}
      </button>
      <button
        className="aito-fab"
        onClick={() => setMobileOpen(true)}
        aria-label="Show Aito info"
        title="Show Aito info"
      >
        <img src="/aito-logo.svg" alt="" className="aito-fab-logo" />
      </button>
      {mobileOpen && (
        <div className="aito-overlay" onClick={closeMobile} />
      )}
      <aside className={`aito-panel${collapsed ? " collapsed" : ""}${mobileOpen ? " open" : ""}`}>
      <button
        className="aito-mobile-close"
        onClick={closeMobile}
        aria-label="Close info panel"
      >
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M3.5 3.5l9 9m-9 0l9-9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
      </button>
      <div className="aito-header">
        <div className="aito-logo-row">
          <img src="/aito-logo.svg" alt="Aito.ai" className="aito-logo-img" />
          <span className="aito-tagline">The Predictive DB</span>
        </div>
      </div>

      <div className="aito-stats">
        {stats.map((s, i) => (
          <div key={i} className="aito-stat">
            <span className="aito-stat-val">{s.value}</span>
            <span className="aito-stat-lbl">{s.label}</span>
          </div>
        ))}
      </div>

      {/* Middle is the only scrollable region — header/stats and CTA
          stay pinned, so the "Start free trial" button is reachable
          on any viewport height without hunting for an inner scroll. */}
      <div className="aito-panel-scroll">
      {tourOn && config.flow_steps && config.flow_steps.length > 0 && (
        <div className="aito-section">
          <div className="aito-section-title" style={{ color: "var(--gold-mid)" }}>Data flow on this page</div>
          {config.flow_steps.map((step) => (
            <div key={step.n} className="tour-step">
              <span className="tour-badge">{step.n}</span>
              <strong>{step.produces}</strong>
              <div style={{ marginTop: 2, fontFamily: "'IBM Plex Mono', monospace", fontSize: 10.5, color: "var(--text3)" }}>
                {step.call}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="aito-section">
        <div className="aito-endpoints">
          <span className="aito-tag">{config.operation}</span>
        </div>
        <div className="aito-desc" dangerouslySetInnerHTML={{ __html: config.description }} />
      </div>

      <div className="aito-section">
        <div className="aito-section-title">
          {lastQuery ? "Last query" : "Example query"}
          {lastResponseMs != null && (
            <span style={{ marginLeft: 8, color: "var(--aito-accent)", fontFamily: "'IBM Plex Mono', monospace", fontWeight: 500, textTransform: "none", letterSpacing: 0 }}>
              {lastResponseMs}ms
            </span>
          )}
        </div>
        <pre className="code-block">
          <code>{lastQuery ? JSON.stringify(lastQuery, null, 2) : exampleQuery}</code>
        </pre>
      </div>

      <div className="aito-section">
        <div className="aito-section-title">Verify yourself</div>
        <div style={{ fontSize: 11.5, color: "rgba(240,240,240,0.85)", lineHeight: 1.55, marginBottom: 10 }}>
          Every claim on this page traces back to an Aito query. No
          separate model file — Aito predicts directly from its index.
        </div>
        <div className="aito-links">
          <a className="aito-link" href="/api/schema" target="_blank" rel="noreferrer">
            <IconBook /> View live schema (JSON)
          </a>
          <a className="aito-link" href="https://aito.ai/docs/api/" target="_blank" rel="noreferrer">
            <IconExternal /> Query API reference
          </a>
        </div>
        <div className="aito-note">
          <strong>Note:</strong> GL codes (4100, 5300, 6200…) are
          illustrative — real Finnish Liikekirjuri uses different
          numbering. Chosen for demo readability.
        </div>
      </div>

      <div className="aito-section">
        <div className="aito-section-title">Learn more</div>
        <div className="aito-links">
          {config.links.map((link, i) => (
            <a key={i} className="aito-link" href={link.url} target="_blank" rel="noreferrer">
              {linkIcon(link.label)} {link.label}
            </a>
          ))}
        </div>
      </div>

      </div>
      <div className="cta-wrap">
        <a className="cta-btn" href="https://console.aito.ai/account/authentication/?signUp=true" target="_blank" rel="noreferrer">
          Start free trial <span>&rarr;</span>
        </a>
      </div>
      </aside>
    </>
  );
}
