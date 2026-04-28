"use client";

import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from "react";
import { apiFetch } from "./api";
import { loadDemoToday } from "./demo-time";

interface Customer {
  customer_id: string;
  name: string;
  size_tier: string;
  invoice_count: number;
  employee_count: number;
}

interface CustomerContextType {
  customerId: string;
  setCustomerId: (id: string) => void;
  customers: Customer[];
  currentCustomer: Customer | null;
}

const CustomerContext = createContext<CustomerContextType>({
  customerId: "",
  setCustomerId: () => {},
  customers: [],
  currentCustomer: null,
});

const STORAGE_KEY = "predictive-ledger-customer-id";

function readInitialCustomer(): string {
  // Resolve initial customer in priority order:
  //   1. ?customer_id=CUST-0042 in the URL (shareable links)
  //   2. localStorage (returning user's last selection)
  //   3. CUST-0000 fallback
  if (typeof window === "undefined") return "CUST-0000";
  const url = new URL(window.location.href);
  const fromUrl = url.searchParams.get("customer_id");
  if (fromUrl && /^CUST-\d{4}$/.test(fromUrl)) return fromUrl;
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored && /^CUST-\d{4}$/.test(stored)) return stored;
  return "CUST-0000";
}

export function CustomerProvider({ children }: { children: ReactNode }) {
  const [customerId, setCustomerIdState] = useState<string>("CUST-0000");
  const [customers, setCustomers] = useState<Customer[]>([]);

  // Read URL/localStorage on mount (window is undefined during SSR/static export)
  useEffect(() => {
    setCustomerIdState(readInitialCustomer());
  }, []);

  // Persist on change + reflect in URL so the link the user copies is shareable.
  const setCustomerId = useCallback((id: string) => {
    setCustomerIdState(id);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, id);
      const url = new URL(window.location.href);
      if (url.searchParams.get("customer_id") !== id) {
        url.searchParams.set("customer_id", id);
        window.history.replaceState({}, "", url.toString());
      }
    }
  }, []);

  // If the URL changes (back/forward), pick that up.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onPop = () => {
      const url = new URL(window.location.href);
      const fromUrl = url.searchParams.get("customer_id");
      if (fromUrl && /^CUST-\d{4}$/.test(fromUrl)) setCustomerIdState(fromUrl);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    apiFetch<{ customers: Customer[] }>("/api/customers")
      .then((d) => setCustomers(d.customers))
      .catch(() => {});
    // Pre-load the demo's frozen "today" so date math is consistent.
    loadDemoToday();
  }, []);

  const currentCustomer = customers.find((c) => c.customer_id === customerId) || null;

  return (
    <CustomerContext.Provider value={{ customerId, setCustomerId, customers, currentCustomer }}>
      {children}
    </CustomerContext.Provider>
  );
}

export function useCustomer() {
  return useContext(CustomerContext);
}
