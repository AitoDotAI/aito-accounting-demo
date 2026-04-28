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

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    // Try to extract the structured error message the API returns
    // for validation failures (e.g. unknown customer_id).
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
