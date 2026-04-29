"use client";

import { useEffect, useRef, useState } from "react";
import { useCustomer } from "@/lib/customer-context";
import { apiFetch } from "@/lib/api";

interface CacheStatus {
  invoices_warm: boolean;
  quality_warm: boolean;
}

interface Customer {
  customer_id: string;
  name: string;
  size_tier: string;
  invoice_count: number;
  employee_count: number;
}

const TIER_ORDER = ["enterprise", "large", "midmarket", "small"] as const;

export default function CustomerSelector() {
  const { customerId, setCustomerId, customers, currentCustomer } = useCustomer();
  const [warm, setWarm] = useState(false);
  const [warmIds, setWarmIds] = useState<Set<string>>(new Set());
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const ref = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  // Computed when the popup opens, used for position: fixed coords.
  const [popupPos, setPopupPos] = useState<{ top: number; right: number } | null>(null);

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

  // One-shot fetch on mount: which customers have precomputed JSON?
  useEffect(() => {
    apiFetch<{ customer_ids: string[] }>("/api/cache/warm_customers")
      .then((d) => setWarmIds(new Set(d.customer_ids)))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  useEffect(() => {
    if (open) {
      inputRef.current?.focus();
      // Compute popup position from the button's bounding rect, so
      // position: fixed places it correctly relative to viewport
      // (and escapes any parent stacking context).
      const rect = buttonRef.current?.getBoundingClientRect();
      if (rect) {
        setPopupPos({
          top: rect.bottom + 4,
          right: window.innerWidth - rect.right,
        });
      }
    }
  }, [open]);

  // Group customers by tier; filter by query
  const filtered = customers.filter((c) => {
    if (!query) return true;
    const q = query.toLowerCase();
    return (
      c.customer_id.toLowerCase().includes(q) ||
      c.name.toLowerCase().includes(q) ||
      c.size_tier.toLowerCase().includes(q)
    );
  });
  const grouped: Record<string, Customer[]> = {};
  for (const c of filtered) {
    (grouped[c.size_tier] ||= []).push(c);
  }

  const select = (id: string) => {
    setCustomerId(id);
    setOpen(false);
    setQuery("");
  };

  return (
    <div ref={ref} style={{ position: "relative", display: "flex", alignItems: "center", gap: 8 }}>
      <span
        title={warm ? "Cached — instant load" : "Cold — first load may take 10-20s"}
        style={{
          width: 8, height: 8, borderRadius: "50%",
          background: warm ? "#6ab87a" : "#d49b4a",
          boxShadow: warm ? "0 0 4px #6ab87a" : "0 0 4px #d49b4a",
        }}
      />
      <button
        ref={buttonRef}
        onClick={() => setOpen(!open)}
        style={{
          padding: "5px 10px",
          borderRadius: 6,
          border: "1px solid var(--border)",
          fontSize: 12,
          fontFamily: "inherit",
          background: "var(--surface)",
          color: "var(--text)",
          cursor: "pointer",
          minWidth: 280,
          textAlign: "left",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 6,
        }}
      >
        <span style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", lineHeight: 1.2, minWidth: 0 }}>
          {currentCustomer ? (
            <>
              <span style={{ fontWeight: 500, fontSize: 12, color: "var(--text)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 240 }}>
                {currentCustomer.name}
              </span>
              <span style={{ fontSize: 10, color: "var(--text3)", fontFamily: "'IBM Plex Mono', monospace" }}>
                {currentCustomer.customer_id} · {currentCustomer.size_tier} · {currentCustomer.invoice_count.toLocaleString()} inv
              </span>
            </>
          ) : (
            customerId
          )}
        </span>
        <span style={{ color: "var(--text3)", fontSize: 10 }}>{open ? "▴" : "▾"}</span>
      </button>

      {open && popupPos && (
        <div
          style={{
            position: "fixed",
            top: popupPos.top,
            right: popupPos.right,
            width: 320,
            maxHeight: 420,
            overflowY: "auto",
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            boxShadow: "0 4px 16px rgba(0,0,0,0.15)",
            zIndex: 1000,
          }}
        >
          <div style={{ padding: 8, borderBottom: "1px solid var(--border2)", position: "sticky", top: 0, background: "var(--surface)" }}>
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by id, tier, name..."
              style={{
                width: "100%",
                padding: "6px 10px",
                fontSize: 12,
                border: "1px solid var(--border)",
                borderRadius: 4,
                background: "var(--surface2)",
                color: "var(--text)",
                outline: "none",
              }}
            />
          </div>
          {filtered.length === 0 && (
            <div style={{ padding: 16, fontSize: 12, color: "var(--text3)", textAlign: "center" }}>No customers match "{query}"</div>
          )}
          {TIER_ORDER.map((tier) => {
            const list = grouped[tier];
            if (!list || list.length === 0) return null;
            return (
              <div key={tier}>
                <div style={{ padding: "6px 10px", fontSize: 10, fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", background: "var(--surface2)", borderBottom: "1px solid var(--border2)" }}>
                  {tier} · {list.length}
                </div>
                {list.map((c) => (
                  <div
                    key={c.customer_id}
                    onClick={() => select(c.customer_id)}
                    style={{
                      padding: "8px 10px",
                      fontSize: 12,
                      cursor: "pointer",
                      background: c.customer_id === customerId ? "var(--gold-light)" : "transparent",
                      borderBottom: "1px solid var(--border2)",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      gap: 8,
                    }}
                    onMouseEnter={(e) => { if (c.customer_id !== customerId) (e.currentTarget as HTMLDivElement).style.background = "var(--surface2)"; }}
                    onMouseLeave={(e) => { if (c.customer_id !== customerId) (e.currentTarget as HTMLDivElement).style.background = "transparent"; }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
                      <span
                        title={warmIds.has(c.customer_id) ? "Cached — instant load" : "Cold — first load may take 10-20s"}
                        style={{
                          width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
                          background: warmIds.has(c.customer_id) ? "#6ab87a" : "#d49b4a",
                        }}
                      />
                      <div style={{ display: "flex", flexDirection: "column", minWidth: 0, overflow: "hidden" }}>
                        <span style={{ fontWeight: 500, color: "var(--text)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                          {c.name}
                        </span>
                        <span style={{ fontSize: 10, color: "var(--text3)", fontFamily: "'IBM Plex Mono', monospace" }}>
                          {c.customer_id} · {c.employee_count} employees
                        </span>
                      </div>
                    </div>
                    <span style={{ fontSize: 11, color: "var(--text2)", whiteSpace: "nowrap" }}>
                      {c.invoice_count.toLocaleString()} inv
                    </span>
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
