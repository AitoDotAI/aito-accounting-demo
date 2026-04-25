"use client";

import { useCustomer } from "@/lib/customer-context";

export default function CustomerSelector() {
  const { customerId, setCustomerId, customers, currentCustomer } = useCustomer();

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
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
