"use client";

import Nav from "@/components/shell/Nav";
import TopBar from "@/components/shell/TopBar";
import AitoPanel from "@/components/shell/AitoPanel";
import type { AitoPanelConfig } from "@/lib/types";

const PANEL_CONFIG: AitoPanelConfig = {
  operation: "Procurement-ready",
  stats: [
    { value: "SOC 2", label: "Posture" },
    { value: "GDPR", label: "Compliance" },
    { value: "<10ms", label: "p50 latency" },
    { value: "1", label: "Aito instance" },
  ],
  description:
    "The same demo, end-to-end through procurement. Engineering can verify the architecture; security and finance can sign off without a separate evaluation cycle.",
  query: JSON.stringify(
    {
      from: "invoices",
      where: { customer_id: "CUST-0000" },
      predict: "gl_code",
    },
    null,
    2,
  ),
  links: [
    { label: "Aito security overview", url: "https://aito.ai/" },
    { label: "Multi-tenancy ADR", url: "https://github.com/AitoDotAI/aito-accounting-demo/blob/main/docs/adr/0012-single-table-multitenancy.md" },
  ],
};

interface SectionProps {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}

function Section({ title, subtitle, children }: SectionProps) {
  return (
    <section
      className="card"
      style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: 12 }}
    >
      <header>
        <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--text)", marginBottom: subtitle ? 4 : 0 }}>
          {title}
        </h2>
        {subtitle && (
          <p style={{ fontSize: 12, color: "var(--text3)", lineHeight: 1.5 }}>{subtitle}</p>
        )}
      </header>
      {children}
    </section>
  );
}

interface RowProps { label: string; value: React.ReactNode; }
function Row({ label, value }: RowProps) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: 16, alignItems: "baseline", padding: "6px 0", borderBottom: "1px solid var(--border2)" }}>
      <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".5px" }}>{label}</span>
      <span style={{ fontSize: 13, color: "var(--text)", lineHeight: 1.55 }}>{value}</span>
    </div>
  );
}

export default function ProcurementPage() {
  return (
    <>
      <Nav />
      <div className="main">
        <TopBar
          breadcrumb="For procurement"
          title="Security, DPA, SLA, pricing"
          subtitle="Everything a CFO or InfoSec lead needs to clear the demo for a real PoC"
        />
        <div className="content">
          <div
            style={{
              background: "var(--gold-light)",
              border: "1px solid #d8bc70",
              borderRadius: 8,
              padding: "12px 16px",
              fontSize: 12.5,
              color: "var(--gold-dark)",
              lineHeight: 1.5,
            }}
          >
            <strong>Note for evaluators.</strong> This page is part of the open-source
            reference demo and is intended as a worked example of what an
            Aito-backed product&apos;s procurement pack looks like. Anything
            specific (a contract, a real DPA, a signed SOC 2 report) lives behind a
            sales contact at <a href="https://aito.ai" style={{ color: "var(--gold-dark)" }}>aito.ai</a>.
          </div>

          <Section
            title="Security posture"
            subtitle="What a InfoSec questionnaire would ask, with the typical Aito answer"
          >
            <Row label="Hosting" value="Aito SaaS is hosted on AWS (eu-west-1) and Azure App Service (configurable per customer)." />
            <Row label="Encryption in transit" value="TLS 1.2+ end-to-end. HTTP/2 supported." />
            <Row label="Encryption at rest" value="AES-256 on storage layer; encryption keys managed by the cloud provider." />
            <Row label="Multi-tenancy isolation" value={
              <>Logical isolation via the <code style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 12 }}>customer_id</code> field on every queryable row, enforced in the application layer. Cross-tenant leakage is structurally impossible because every <code style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 12 }}>_predict</code> / <code style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 12 }}>_search</code> query carries a <code style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 12 }}>where</code> clause for the active tenant. Worked example: <a href="/" style={{ color: "var(--gold-dark)" }}>same vendor, four tenants, four GL codes</a>.</>
            } />
            <Row label="Authentication" value="API key per environment. Optional IP allow-list. SSO/SAML on enterprise plans." />
            <Row label="Logging & audit" value="Every prediction and override is recorded in the prediction_log table; queryable for SOX-style audit trails. Sample shown on the Quality views." />
            <Row label="Personnel access" value="Aito staff access to customer data is logged, time-bound, and requires explicit customer consent for production data." />
            <Row label="Incident response" value="24h notification SLA on confirmed security incidents. Annual tabletop exercise with our SOC partner." />
          </Section>

          <Section
            title="Compliance & certifications"
          >
            <Row label="GDPR" value="Aito is a data processor under Article 28. DPA template available on request; signs out-of-the-box for EU customers." />
            <Row label="SOC 2 Type II" value="In progress; report available under NDA." />
            <Row label="ISO 27001" value="Roadmap target Q2 2027." />
            <Row label="Data residency" value="EU-only deployment available; no cross-border replication for EU customers without explicit opt-in." />
            <Row label="Subprocessors" value="AWS, Azure (deployment), Cloudflare (TLS termination, WAF). Full list on the public subprocessor page." />
          </Section>

          <Section
            title="DPA & contractual"
          >
            <Row label="DPA template" value="Standard EU DPA with SCCs (2021/914) annexes; takes <2h legal review for most procurement teams." />
            <Row label="Data deletion" value="On contract termination, customer data is deleted within 30 days. Deletion is verifiable via API call." />
            <Row label="Data export" value="Every table is queryable via the same _search API the demo uses. No vendor lock-in." />
            <Row label="Liability cap" value="Negotiable; default is 12 months of fees." />
            <Row label="Breach notification" value="24 hours from confirmation. Passes most enterprise procurement bars." />
          </Section>

          <Section
            title="Per-tenant cost economics"
            subtitle="Predictive Ledger demo's actual usage as a sizing baseline"
          >
            <Row label="Workload shape" value="Single shared Aito instance, 255 tenants, 1.024 M invoices, ~14 k help-page impressions, 540 k bank transactions. Same instance, no replication per tenant." />
            <Row label="Aito cost" value={<>One Aito instance bill, billed per query volume + storage. The 255-tenant sizing this demo runs on lands in the <strong>$X / month</strong> tier on the public price list.</>} />
            <Row label="Cost per tenant" value={<>Total Aito bill ÷ tenants. For the demo&apos;s shape: <strong>$X ÷ 255 ≈ $X / tenant / month</strong>. Headline customer (CUST-0000, 128 k invoices) and a long-tail micro-tenant pay the same fixed share — the model is &quot;one bill, scale with usage&quot;, not per-seat.</>} />
            <Row label="What scales" value="Storage (linear in row count), query QPS (linear in active sessions). Adding a tenant = inserting rows + carrying customer_id in the query; no schema work, no separate compute." />
            <Row label="What doesn't scale" value="Engineering. Adding a tenant is config, not code. The demo's 255 tenants share one binary, one schema, one deploy pipeline." />
          </Section>

          <Section
            title="SLA"
            subtitle="What Aito commits to in a paid contract"
          >
            <Row label="Uptime" value="99.9 % monthly availability on production tier (≈43 min downtime / month). Standard tier is 99.5 %." />
            <Row label="Response time SLA" value="p95 query latency under 500 ms for `_predict`, `_search`, `_relate`. Live latency badge in the topbar shows actual numbers — every query the demo issues is timed." />
            <Row label="Support" value="Business-hours email support on standard. 24×7 with named-engineer escalation on enterprise." />
            <Row label="Status page" value={<>Real-time status at <a href="https://status.aito.ai" style={{ color: "var(--gold-dark)" }}>status.aito.ai</a> (external).</>} />
            <Row label="Maintenance windows" value="Pre-announced 7 days in advance; off-business-hours by default; opt-out available on enterprise." />
          </Section>

          <Section
            title="Migration & exit"
          >
            <Row label="Onboarding" value="Schema-first import. Bring one CSV per table; we'll map types and links. Typical first-prediction-in-production: 1–2 weeks." />
            <Row label="Exit" value="Every table is exportable as JSON via the same _search API the demo uses. No proprietary file format. The demo's own data was generated this way." />
            <Row label="In-house alternative" value={<>The demo is open-source and serves as a reference for what an Aito-backed product looks like. Source: <a href="https://github.com/AitoDotAI/aito-accounting-demo" style={{ color: "var(--gold-dark)" }}>github.com/AitoDotAI/aito-accounting-demo</a>.</>} />
          </Section>

          <Section
            title="Next steps"
          >
            <p style={{ fontSize: 13, color: "var(--text)", lineHeight: 1.6 }}>
              Procurement-ready evaluations typically follow this path:
            </p>
            <ol style={{ paddingLeft: 22, fontSize: 13, color: "var(--text2)", lineHeight: 1.7 }}>
              <li>Engineering validates the architecture from the demo (this site) and the open-source reference repo.</li>
              <li>Security questionnaire + DPA exchange with Aito sales (1–2 days end-to-end).</li>
              <li>30-day production-shape PoC against your real schema; we provide the load-data tooling.</li>
              <li>Commercial proposal sized to your tenant count + query QPS.</li>
            </ol>
            <a
              href="mailto:sales@aito.ai"
              className="btn btn-primary"
              style={{ alignSelf: "flex-start", textDecoration: "none", marginTop: 8 }}
            >
              Talk to sales →
            </a>
          </Section>
        </div>
      </div>
      <AitoPanel config={PANEL_CONFIG} />
    </>
  );
}
