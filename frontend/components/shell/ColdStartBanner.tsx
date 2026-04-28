"use client";

import { useCustomer } from "@/lib/customer-context";

// Matches the precompute --lite-threshold: customers below this
// invoice count ship with empty matching/anomalies/rule-mining/
// quality JSON, because at that scale the patterns aren't reliably
// learnable yet. The banner sets that expectation up-front.
const LITE_THRESHOLD = 1500;
const COLD_START_THRESHOLD = 100;

export default function ColdStartBanner() {
  const { currentCustomer } = useCustomer();
  if (!currentCustomer) return null;

  const n = currentCustomer.invoice_count;
  if (n >= LITE_THRESHOLD) return null;

  // Differentiate the two regimes: very-cold vs sub-threshold but
  // still has some data.
  const veryCold = n < COLD_START_THRESHOLD;
  return (
    <div
      style={{
        background: "var(--surface2)",
        border: "1px solid var(--border2)",
        borderLeft: "3px solid var(--amber)",
        padding: "8px 14px",
        fontSize: "12px",
        color: "var(--text2)",
        margin: "0 0 12px",
        lineHeight: 1.5,
      }}
    >
      <strong style={{ color: "var(--amber)", marginRight: 6 }}>
        {veryCold ? "Cold start:" : "Just signed up:"}
      </strong>
      {currentCustomer.customer_id} has {n.toLocaleString()} invoices —{" "}
      {veryCold
        ? "Aito predictions still work but with honest low confidence on rarely-seen vendors. The system tells you 'I don't have enough data yet' instead of guessing."
        : "rule-mining, anomaly detection, payment matching, and override patterns need at least a few thousand invoices to surface reliably. The Invoice Processing and Form Fill views still work; aggregate views show empty until the customer accumulates more history."}
      {" "}Switch to <strong>CUST-0000</strong> ({(16000).toLocaleString()} invoices) to see the full demo at scale.
    </div>
  );
}
