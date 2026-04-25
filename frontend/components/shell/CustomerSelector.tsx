"use client";

import { useEffect, useState } from "react";
import { useCustomer } from "@/lib/customer-context";
import { apiFetch } from "@/lib/api";

interface CacheStatus {
  invoices_warm: boolean;
  quality_warm: boolean;
}

export default function CustomerSelector() {
  const { customerId, setCustomerId, customers, currentCustomer } = useCustomer();
  const [warm, setWarm] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const check = () => {
      apiFetch<CacheStatus>(`/api/cache/status?customer_id=${customerId}`)
        .then((d) => { if (!cancelled) setWarm(d.invoices_warm); })
        .catch(() => {});
    };
    check();
    const interval = setInterval(check, 5000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [customerId]);

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span
        title={warm ? "Cached — instant load" : "Cold — first load may take 10-20s"}
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: warm ? "#6ab87a" : "#d49b4a",
          boxShadow: warm ? "0 0 4px #6ab87a" : "0 0 4px #d49b4a",
        }}
      />
      <select
        value={customerId}
        onChange={(e) => setCustomerId(e.target.value)}
        style={{
          padding: "5px 10px",
          borderRadius: 6,
          border: "1px solid var(--border)",
          fontSize: 12,
          fontFamily: "inherit",
          background: "var(--surface)",
          color: "var(--text)",
          cursor: "pointer",
          minWidth: 180,
        }}
      >
        {customers.map((c) => (
          <option key={c.customer_id} value={c.customer_id}>
            {c.customer_id} — {c.size_tier} ({c.invoice_count.toLocaleString()})
          </option>
        ))}
      </select>
      {currentCustomer && (
        <span style={{ fontSize: 11, color: "var(--text3)" }}>
          {currentCustomer.employee_count} employees
        </span>
      )}
    </div>
  );
}
