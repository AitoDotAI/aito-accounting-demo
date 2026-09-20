const API_BASE = typeof window !== "undefined"
  ? `${window.location.protocol}//${window.location.host}`
  : "";

export class ApiError extends Error {
  status: number;
  detail: string | null;
  constructor(status: number, detail: string | null, path: string) {
    super(detail || `API ${status}: ${path}`);
    this.status = status;
    this.detail = detail;
  }
}

export interface AitoLatencySample {
  ms: number;
  calls: number;
  path: string;
  at: number;
  /** Per-Aito-call breakdown: e.g. [{op:"_predict", ms:28.4}, {op:"_relate", ms:142.0}].
   *  Sourced from the X-Aito-Ops response header. Empty when the request
   *  didn't hit Aito or the backend is older than the per-op breakdown. */
  ops: { op: string; ms: number }[];
}

type LatencyListener = (sample: AitoLatencySample) => void;
const latencyListeners = new Set<LatencyListener>();

// Marker so an aggressive auto-reload can't loop. sessionStorage scope
// = one auto-recovery attempt per tab visit.
const STALE_STATE_RECOVERY_KEY = "aitoStaleStateRecoveryAttempted";

/** Best-effort recovery from a fetch-level TypeError ("Failed to fetch" /
 *  "Load failed"). The most common cause in this demo is a stale cached
 *  HTML+JS bundle from before nginx started sending `Cache-Control: no-
 *  store` on HTML — an old bundle issues requests the current backend
 *  doesn't satisfy and fetch() rejects with a TypeError. Clear local
 *  state + reload to force a fresh HTML fetch and current bundle hashes.
 *
 *  Returns true when a reload was triggered so the caller can stall
 *  instead of surfacing the original error to the user mid-navigation. */
async function tryStaleStateRecovery(): Promise<boolean> {
  if (typeof window === "undefined") return false;
  if (window.sessionStorage.getItem(STALE_STATE_RECOVERY_KEY) === "1") return false;
  window.sessionStorage.setItem(STALE_STATE_RECOVERY_KEY, "1");
  try { window.localStorage.clear(); } catch { /* private mode etc. */ }
  try {
    if (typeof caches !== "undefined") {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
    }
  } catch { /* CacheStorage may be denied */ }
  window.location.reload();
  return true;
}

export function onAitoLatency(fn: LatencyListener): () => void {
  latencyListeners.add(fn);
  return () => {
    // Set.delete() returns boolean; a void cleanup callback is what
    // React effects expect, so wrap explicitly rather than rely on
    // type coercion.
    latencyListeners.delete(fn);
  };
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch (err) {
    // TypeError from fetch() = network-level failure (offline, DNS, TLS,
    // request aborted by extension/data-saver, *or* — most common cause
    // for this demo's existing prospects — a stale cached bundle).
    // Try a one-shot self-heal. On success the page is reloading, so
    // return a never-resolving promise to stop the caller from briefly
    // rendering its error UI before navigation completes.
    if (err instanceof TypeError && await tryStaleStateRecovery()) {
      return new Promise<T>(() => { /* page is reloading */ });
    }
    throw err;
  }
  // Surface Aito round-trip ms whenever the backend signals it via
  // X-Aito-Ms (set per-request when any AitoClient call ran). Listeners
  // power the topbar latency badge; endpoints that didn't hit Aito
  // simply emit nothing.
  const ms = res.headers.get("X-Aito-Ms");
  const calls = res.headers.get("X-Aito-Calls");
  const opsHeader = res.headers.get("X-Aito-Ops");
  if (ms != null) {
    const ops = opsHeader
      ? opsHeader.split(",").map((entry) => {
          const i = entry.lastIndexOf(":");
          return i < 0
            ? { op: entry, ms: NaN }
            : { op: entry.slice(0, i), ms: parseFloat(entry.slice(i + 1)) };
        })
      : [];
    const sample: AitoLatencySample = {
      ms: parseFloat(ms),
      calls: parseInt(calls || "1", 10) || 1,
      path,
      at: Date.now(),
      ops,
    };
    for (const fn of latencyListeners) {
      try { fn(sample); } catch { /* listener error must not break API call */ }
    }
  }
  if (!res.ok) {
    let detail: string | null = null;
    try {
      const body = await res.clone().json();
      detail = body?.error || body?.detail || null;
    } catch {}
    throw new ApiError(res.status, detail, path);
  }
  return res.json();
}

export function fmtAmount(n: number): string {
  return "\u20AC" + n.toLocaleString("fi-FI", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function confClass(p: number): string {
  if (p >= 0.80) return "conf-high";
  if (p >= 0.50) return "conf-mid";
  return "conf-low";
}
