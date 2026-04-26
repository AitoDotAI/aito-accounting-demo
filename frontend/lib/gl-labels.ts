// Centralized GL code → human label map. Keep in sync with
// backend src/invoice_service.py GL_LABELS and data/generate_fixtures.py.
//
// IMPORTANT: these are illustrative codes, not real Finnish FAS /
// Liikekirjuri numbering (e.g. real Liikekirjuri puts materiaalit ja
// palvelut at 4000–4099, henkilöstökulut at 5000–5099). They were
// chosen for readability in the demo. Use GL_DISCLAIMER below in
// tooltips and footers wherever GL codes are surfaced.

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

export const GL_DISCLAIMER =
  "Illustrative chart of accounts. Real Finnish Liikekirjuri / FAS uses different numbering — these are for demo readability.";

export function glLabel(code: string | null | undefined): string {
  if (!code) return "—";
  return GL_LABELS[code] ?? code;
}

export function glDisplay(code: string | null | undefined): string {
  if (!code) return "—";
  const label = GL_LABELS[code];
  return label ? `${code} — ${label}` : code;
}
