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
  /** False until the URL / localStorage have been read: data hooks must not
   *  request anything for `customerId` before then, it is only the default. */
  customerResolved: boolean;
  setCustomerId: (id: string) => void;
  customers: Customer[];
  currentCustomer: Customer | null;
}

const CustomerContext = createContext<CustomerContextType>({
  customerId: "",
  customerResolved: false,
  setCustomerId: () => {},
  customers: [],
  currentCustomer: null,
});

const STORAGE_KEY = "predictive-ledger-customer-id";

// The first tenant a visitor sees. CUST-0000 is almost entirely coded by
// rules and its anomaly scan comes back empty, so it shows nothing for
// Aito to do; CUST-0001 has a real mix of rule, predicted and flagged work.
export const DEFAULT_CUSTOMER = "CUST-0001";

function readInitialCustomer(): string {
  // Resolve initial customer in priority order:
  //   1. ?customer_id=CUST-0042 in the URL (shareable links)
  //   2. localStorage (returning user's last selection)
  //   3. DEFAULT_CUSTOMER
  if (typeof window === "undefined") return DEFAULT_CUSTOMER;
  const url = new URL(window.location.href);
  const fromUrl = url.searchParams.get("customer_id");
  if (fromUrl && /^CUST-\d{4}$/.test(fromUrl)) return fromUrl;
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored && /^CUST-\d{4}$/.test(stored)) return stored;
  return DEFAULT_CUSTOMER;
}

export function CustomerProvider({ children }: { children: ReactNode }) {
  const [customerId, setCustomerIdState] = useState<string>(DEFAULT_CUSTOMER);
  const [customerResolved, setCustomerResolved] = useState(false);
  const [customers, setCustomers] = useState<Customer[]>([]);

  // Read URL/localStorage on mount (window is undefined during SSR/static
  // export). What renders does not change until this runs, so the prerendered
  // HTML still matches; what changes is that data hooks wait for
  // `customerResolved` before requesting anything: their effects run on the
  // first render, and with only the default known they asked for CUST-0001's
  // data (a live Aito query) before the URL's customer was read.
  useEffect(() => {
    setCustomerIdState(readInitialCustomer());
    setCustomerResolved(true);
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
    <CustomerContext.Provider value={{ customerId, customerResolved, setCustomerId, customers, currentCustomer }}>
      {children}
    </CustomerContext.Provider>
  );
}

export function useCustomer() {
  return useContext(CustomerContext);
}
