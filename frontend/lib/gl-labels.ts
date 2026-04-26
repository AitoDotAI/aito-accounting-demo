// Centralized GL code → human label map. Keep in sync with
// backend src/invoice_service.py GL_LABELS and data/generate_fixtures.py.

export const GL_LABELS: Record<string, string> = {
  "4100": "COGS",
  "4400": "Materials & Supplies",
  "4500": "Office Expenses",
  "4600": "Logistics",
  "5100": "Facilities",
  "5200": "Maintenance",
  "5300": "Insurance",
  "5400": "Professional Services",
  "6100": "IT & Software",
  "6200": "Telecom",
};

export function glLabel(code: string | null | undefined): string {
  if (!code) return "—";
  return GL_LABELS[code] ?? code;
}

export function glDisplay(code: string | null | undefined): string {
  if (!code) return "—";
  const label = GL_LABELS[code];
  return label ? `${code} — ${label}` : code;
}
