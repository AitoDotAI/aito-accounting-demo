"use client";

import { useEffect, useState } from "react";
import { useCustomer } from "@/lib/customer-context";

const KEY = "predictive-ledger-banner-dismissed";

/**
 * Above-the-fold one-line framing of what this demo is. Dismissible
 * via X; preference persisted in localStorage so repeat visitors
 * don't see it again.
 */
export default function HeadlineBanner() {
  const { customers } = useCustomer();
  const [dismissed, setDismissed] = useState(true);

  useEffect(() => {
    if (typeof window === "undefined") return;
    setDismissed(localStorage.getItem(KEY) === "1");
  }, []);

  if (dismissed) return null;

  const total = customers.reduce((sum, c) => sum + (c.invoice_count ?? 0), 0);
  const totalLabel = total > 0 ? `${customers.length} customers · ${total.toLocaleString()} invoices` : "256 customers";

  const dismiss = () => {
    localStorage.setItem(KEY, "1");
    setDismissed(true);
  };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 16,
        background: "linear-gradient(90deg, var(--gold-dark) 0%, var(--gold-mid) 100%)",
        color: "#0d1520",
        padding: "8px 16px",
        fontSize: "12.5px",
        fontWeight: 500,
        borderBottom: "1px solid var(--gold-dark)",
      }}
    >
      <span>
        <strong>Predictive Ledger</strong> · reference implementation
        for developers building on Aito.ai (not a packaged product) ·
        multi-tenant AP demo: {totalLabel} in <em>one</em> shared instance ·
        same{" "}
        <code style={{ background: "rgba(13,21,32,.1)", padding: "1px 5px", borderRadius: 3, fontFamily: "'IBM Plex Mono', monospace", fontSize: 11 }}>_predict</code>{" "}
        operator, scoped per customer · no separate model file
      </span>
      <button
        onClick={dismiss}
        title="Dismiss"
        style={{
          background: "transparent",
          border: "none",
          color: "#0d1520",
          cursor: "pointer",
          fontSize: 16,
          fontWeight: 700,
          padding: "0 4px",
          lineHeight: 1,
          opacity: 0.6,
        }}
      >
        ×
      </button>
    </div>
  );
}
