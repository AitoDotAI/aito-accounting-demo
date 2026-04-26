"use client";

import { useCustomer } from "@/lib/customer-context";

const COLD_START_THRESHOLD = 100;

/**
 * Show on every page when the selected customer has too little data
 * for confident predictions. Sets honest expectations: predictions
 * will still work, but with low confidence on novel vendors.
 */
export default function ColdStartBanner() {
  const { currentCustomer } = useCustomer();
  if (!currentCustomer || currentCustomer.invoice_count >= COLD_START_THRESHOLD) {
    return null;
  }
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
      <strong style={{ color: "var(--amber)", marginRight: 6 }}>Cold start:</strong>
      {currentCustomer.customer_id} has only {currentCustomer.invoice_count} invoices.
      Aito predictions still work but with honest low confidence on rarely-seen vendors —
      that's the system telling you "I don't have enough data yet" rather than guessing.
      Switch to a larger customer (e.g. CUST-0000) to see predictions with rich history.
    </div>
  );
}
