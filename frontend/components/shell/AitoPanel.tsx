"use client";

import { useCustomer } from "@/lib/customer-context";
import type { AitoPanelConfig, AitoPanelStat } from "@/lib/types";

interface AitoPanelProps {
  config: AitoPanelConfig;
  lastQuery?: object | null;
  lastResponseMs?: number | null;
}

// Resolve stats that reference live customer data via the special "$" prefix
function resolveStat(stat: AitoPanelStat, ctx: { invoices: number; employees: number }): AitoPanelStat {
  if (stat.value === "$invoices") return { ...stat, value: ctx.invoices.toLocaleString() };
  if (stat.value === "$employees") return { ...stat, value: ctx.employees.toLocaleString() };
  return stat;
}

export default function AitoPanel({ config, lastQuery, lastResponseMs }: AitoPanelProps) {
  const { currentCustomer, customers } = useCustomer();
  const totalInvoices = customers.reduce((sum, c) => sum + (c.invoice_count || 0), 0);
  const ctx = {
    invoices: currentCustomer?.invoice_count ?? totalInvoices,
    employees: currentCustomer?.employee_count ?? 0,
  };
  const stats = config.stats.map((s) => resolveStat(s, ctx));

  return (
    <aside className="aito-panel">
      <div className="aito-header">
        <div className="aito-logo-row">
          <div className="aito-logo">
            <span className="ai">ai</span><span className="to">to..</span>
          </div>
          <span style={{ fontSize: 10, color: "#f0f0f0", padding: "3px 8px", border: "1px solid #2e3480", borderRadius: 4, opacity: 0.8 }}>
            The Predictive DB
          </span>
        </div>
      </div>

      <div className="aito-stats">
        {stats.map((s, i) => (
          <div key={i} className="aito-stat">
            <div className="aito-stat-val">{s.value}</div>
            <div className="aito-stat-lbl">{s.label}</div>
          </div>
        ))}
      </div>

      <div className="aito-section">
        <div className="aito-section-title">This view</div>
        <div className="aito-tag">{config.operation}</div>
        <div className="aito-desc" dangerouslySetInnerHTML={{ __html: config.description }} />
      </div>

      <div className="aito-section">
        <div className="aito-section-title">
          {lastQuery ? "Last query" : "Example query"}
        </div>
        {lastResponseMs != null && (
          <div style={{ fontSize: 10, color: "var(--aito-accent)", marginBottom: 6, fontFamily: "'IBM Plex Mono', monospace" }}>
            Response: {lastResponseMs}ms
          </div>
        )}
        <div className="code-block">
          {lastQuery
            ? JSON.stringify(lastQuery, null, 2)
            : config.query}
        </div>
      </div>

      <div className="aito-section">
        <div className="aito-section-title">Learn more</div>
        <div className="aito-links">
          {config.links.map((link, i) => (
            <a key={i} className="aito-link" href={link.url} target="_blank" rel="noreferrer">
              {link.label}
            </a>
          ))}
        </div>
      </div>

      <div style={{ flex: 1 }} />
      <div className="cta-wrap">
        <a className="cta-btn" href="https://aito.ai" target="_blank" rel="noreferrer" style={{ display: "block", textDecoration: "none" }}>
          Start free trial &rarr;
        </a>
      </div>
    </aside>
  );
}
