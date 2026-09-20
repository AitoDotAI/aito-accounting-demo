"use client";

import { useEffect, useState } from "react";
import { useCustomer } from "@/lib/customer-context";

// Matches the precompute --lite-threshold: customers below this
// invoice count ship with empty matching/anomalies/rule-mining/
// quality JSON, because at that scale the patterns aren't reliably
// learnable yet. The banner sets that expectation up-front.
const LITE_THRESHOLD = 1500;
const COLD_START_THRESHOLD = 100;

// Per-customer dismissal so a user who's seen the banner for one
// tenant doesn't keep getting it on every page nav. Stored on a
// {customer_id} key so switching tenants re-shows the banner once.
const STORAGE_PREFIX = "predictive-ledger-cold-start-dismissed:";

export default function ColdStartBanner() {
  const { currentCustomer } = useCustomer();
  const [dismissed, setDismissed] = useState(true);

  // Read dismissal state when the customer changes. Default to
  // "dismissed=true" so the banner doesn't flash on the first
  // render before localStorage is read.
  useEffect(() => {
    if (typeof window === "undefined" || !currentCustomer) return;
    const key = STORAGE_PREFIX + currentCustomer.customer_id;
    setDismissed(window.localStorage.getItem(key) === "1");
  }, [currentCustomer]);

  if (!currentCustomer) return null;
  const n = currentCustomer.invoice_count;
  if (n >= LITE_THRESHOLD) return null;
  if (dismissed) return null;

  const veryCold = n < COLD_START_THRESHOLD;

  const dismiss = () => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_PREFIX + currentCustomer.customer_id, "1");
    }
    setDismissed(true);
  };

  return (
    <div
      style={{
        background: "var(--surface2)",
        border: "1px solid var(--border2)",
        borderLeft: "3px solid var(--amber)",
        padding: "8px 36px 8px 14px",
        fontSize: "12px",
        color: "var(--text2)",
        margin: "0 0 12px",
        lineHeight: 1.5,
        position: "relative",
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
      <button
        onClick={dismiss}
        title="Dismiss for this customer"
        aria-label="Dismiss"
        style={{
          position: "absolute",
          top: 4,
          right: 6,
          background: "transparent",
          border: "none",
          color: "var(--text3)",
          cursor: "pointer",
          fontSize: 16,
          lineHeight: 1,
          padding: "4px 6px",
        }}
      >
        ×
      </button>
    </div>
  );
}
