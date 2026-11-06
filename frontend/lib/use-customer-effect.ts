"use client";

import { useEffect, type DependencyList, type EffectCallback } from "react";
import { useCustomer } from "./customer-context";

/**
 * An effect that fetches for the current customer.
 *
 * It does not run until the customer context has read the URL and
 * localStorage (`customerResolved`). Before that `customerId` is only the
 * default, and a page effect runs on the first render: without the gate,
 * `/matching/?customer_id=X` asked for CUST-0001's data (a live Aito query)
 * and then for X's. Use this instead of `useEffect` for anything that sends a
 * `customer_id`; e2e/first-fetch.test.ts and lib/__tests__/customer-fetch-
 * gate.test.ts fail if a page or component fetches from a bare `useEffect`.
 *
 * `deps` are the effect's own dependencies (usually `[customerId, ...]`); the
 * gate is added here, so callers cannot forget it.
 */
export function useCustomerEffect(effect: EffectCallback, deps: DependencyList): void {
  const { customerResolved } = useCustomer();
  useEffect(() => {
    if (!customerResolved) return;
    return effect();
    // The caller owns the effect's dependency list, as with useEffect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customerResolved, ...deps]);
}
