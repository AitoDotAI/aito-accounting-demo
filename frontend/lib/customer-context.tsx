"use client";

import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { apiFetch } from "./api";

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

export function CustomerProvider({ children }: { children: ReactNode }) {
  const [customerId, setCustomerId] = useState("CUST-0000");
  const [customers, setCustomers] = useState<Customer[]>([]);

  useEffect(() => {
    apiFetch<{ customers: Customer[] }>("/api/customers")
      .then((d) => setCustomers(d.customers))
      .catch(() => {});
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
