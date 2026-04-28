"use client";

import Nav from "@/components/shell/Nav";
import TopBar from "@/components/shell/TopBar";
import AitoPanel from "@/components/shell/AitoPanel";
import { useCustomer } from "@/lib/customer-context";
import type { AitoPanelConfig } from "@/lib/types";

const PANEL: AitoPanelConfig = {
  operation: "outbound webhooks",
  stats: [
    { value: "Sketch", label: "Status" },
    { value: "0", label: "Enabled" },
    { value: "$invoices", label: "Records" },
    { value: "Indexed", label: "Model" },
  ],
  description:
    "Architectural sketch of how predictions and overrides flow back into the customer's ERP. " +
    "Not implemented in this reference — shows the surface where you'd plug in NetSuite, Microsoft Dynamics, Procountor, or your own.",
  query: JSON.stringify({ from: "prediction_log", where: { customer_id: "CUST-0000" }, limit: 50 }, null, 2),
  links: [
    { label: "Aito API reference", url: "https://aito.ai/docs/api/" },
  ],
};

interface Integration {
  id: string;
  name: string;
  category: string;
  notes: string;
  example_payload: string;
}

const INTEGRATIONS: Integration[] = [
  {
    id: "netsuite",
    name: "NetSuite",
    category: "ERP",
    notes:
      "Post each predicted invoice to NetSuite as a draft VendorBill via SOAP/REST. " +
      "Use the prediction_log row's predicted_value as the proposed Account; let the user confirm in the NetSuite UI.",
    example_payload: `POST https://<account>.suitetalk.api.netsuite.com/services/rest/record/v1/vendorBill
{
  "entity":   { "internalid": "<vendor_id>" },
  "tranDate": "2026-04-25",
  "memo":     "Auto-coded by Aito (CUST-0000) — prediction_log id LOG-abc",
  "expense": [{
    "category": { "internalid": "<gl_4400_id>" },
    "amount":   4220.00
  }]
}`,
  },
  {
    id: "dynamics",
    name: "Microsoft Dynamics 365 Finance",
    category: "ERP",
    notes:
      "Use the OData /VendorInvoiceHeaders endpoint to create the header, " +
      "/VendorInvoiceLines for each line. Aito's predicted GL goes into MainAccount; predicted approver routes via the workflow assignment.",
    example_payload: `POST /data/VendorInvoiceHeaders
{
  "DataAreaId": "DAT",
  "InvoiceAccount": "<vendor_id>",
  "InvoiceDate": "2026-04-25",
  "PurchaseOrder": "",
  "InvoiceId": "INV-CUST-0000-001"
}`,
  },
  {
    id: "procountor",
    name: "Procountor (Finnish AP)",
    category: "ERP",
    notes:
      "Procountor's REST API is well-suited because its account / dimension structure " +
      "matches the predicted fields here directly. Each prediction maps cleanly to a single API call.",
    example_payload: `POST https://api.procountor.com/api/purchaseinvoices
{
  "supplier":    { "businessId": "0223640-4" },
  "invoiceDate": "2026-04-25",
  "totalSum":    4220.00,
  "rows": [{
    "accountNumber": "4400",
    "dimensions":    [{ "name": "Cost centre", "value": "CC-210" }],
    "totalSum":      4220.00
  }]
}`,
  },
  {
    id: "outbound_webhook",
    name: "Generic outbound webhook",
    category: "Generic",
    notes:
      "If your ERP isn't listed, point an HTTPS endpoint at the prediction_log table and " +
      "consume new rows on a schedule. Aito predictions and human overrides both end up here, " +
      "so your ERP gets a single feed with provenance.",
    example_payload: `POST <your_endpoint>
{
  "log_id":          "LOG-abc",
  "customer_id":     "CUST-0000",
  "field":           "gl_code",
  "predicted_value": "4400",
  "user_value":      "4400",
  "source":          "predicted",
  "confidence":      0.91,
  "accepted":        true,
  "timestamp":       1714060800
}`,
  },
];

export default function IntegrationsPage() {
  const { customerId } = useCustomer();
  // Substitute the active customer into example payloads so copy-paste
  // produces queries that match the rest of the demo's state.
  const subst = (s: string) => s.replaceAll("CUST-0000", customerId);
  return (
    <>
      <Nav />
      <div className="main">
        <TopBar
          breadcrumb="Setup"
          title="Integrations"
          subtitle="Architectural sketch — how predictions flow into your ERP"
        />
        <div className="content">
          <div style={{ background: "var(--surface2)", border: "1px solid var(--border2)", borderLeft: "3px solid var(--gold-mid)", borderRadius: 4, padding: "12px 16px", marginBottom: 16, fontSize: 12, color: "var(--text2)", lineHeight: 1.6 }}>
            <strong style={{ color: "var(--gold-dark)", marginRight: 6 }}>Sketch only.</strong>
            None of these integrations are wired up in the reference
            implementation. They show the <em>surface</em> where you'd
            plug in your ERP. The shared mechanism is the
            <code style={{ fontFamily: "'IBM Plex Mono', monospace", margin: "0 4px" }}>prediction_log</code>
            table — every field decision (predicted, accepted, overridden) is
            recorded with provenance, ready to feed an outbound webhook.
          </div>

          {INTEGRATIONS.map((it) => (
            <div key={it.id} className="card" style={{ marginBottom: 12 }}>
              <div className="card-header">
                <span className="card-title">{it.name}</span>
                <span className="card-hint">{it.category}</span>
              </div>
              <div style={{ padding: 16 }}>
                <div style={{ fontSize: 12.5, color: "var(--text2)", lineHeight: 1.6, marginBottom: 12 }}>
                  {subst(it.notes)}
                </div>
                <pre style={{
                  background: "var(--surface2)",
                  border: "1px solid var(--border2)",
                  borderRadius: 4,
                  padding: 12,
                  fontSize: 11,
                  fontFamily: "'IBM Plex Mono', monospace",
                  color: "var(--text2)",
                  overflowX: "auto",
                  margin: 0,
                  lineHeight: 1.5,
                }}>
{subst(it.example_payload)}
                </pre>
              </div>
            </div>
          ))}
        </div>
      </div>
      <AitoPanel config={PANEL} />
    </>
  );
}
