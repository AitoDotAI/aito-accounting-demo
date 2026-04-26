/**
 * The demo's frozen "today". Synced from the backend on first call.
 * Frontend never uses `new Date()` for any due-date math — always
 * uses demoToday() so the demo behaves identically across visits and
 * over time.
 */

import { apiFetch } from "./api";

let cached: Date | null = null;
let inflight: Promise<Date> | null = null;

const FALLBACK = new Date("2026-04-30T00:00:00Z");

export async function loadDemoToday(): Promise<Date> {
  if (cached) return cached;
  if (inflight) return inflight;
  inflight = apiFetch<{ date: string }>("/api/demo/today")
    .then((d) => {
      cached = new Date(`${d.date}T00:00:00Z`);
      return cached;
    })
    .catch(() => {
      cached = FALLBACK;
      return cached;
    });
  return inflight;
}

/** Synchronous accessor: returns the cached value or fallback. */
export function demoToday(): Date {
  return cached ?? FALLBACK;
}
