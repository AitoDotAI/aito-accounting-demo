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
}

type LatencyListener = (sample: AitoLatencySample) => void;
const latencyListeners = new Set<LatencyListener>();

export function onAitoLatency(fn: LatencyListener): () => void {
  latencyListeners.add(fn);
  return () => latencyListeners.delete(fn);
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  // Surface Aito round-trip ms whenever the backend signals it via
  // X-Aito-Ms (set per-request when any AitoClient call ran). Listeners
  // power the topbar latency badge; endpoints that didn't hit Aito
  // simply emit nothing.
  const ms = res.headers.get("X-Aito-Ms");
  const calls = res.headers.get("X-Aito-Calls");
  if (ms != null) {
    const sample: AitoLatencySample = {
      ms: parseFloat(ms),
      calls: parseInt(calls || "1", 10) || 1,
      path,
      at: Date.now(),
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
