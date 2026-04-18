export interface InvoicePrediction {
  invoice_id: string;
  vendor: string;
  amount: number;
  approver: string | null;
  approver_confidence: number;
  gl_code: string | null;
  gl_label: string | null;
  gl_confidence: number;
  source: "rule" | "aito" | "review";
  confidence: number;
  gl_alternatives?: Alternative[];
  approver_alternatives?: Alternative[];
}

export interface Alternative {
  value: string;
  display: string;
  confidence: number;
  why?: WhyFactor[];
}

export interface WhyFactor {
  field: string;
  value: string;
  lift: number;
}

export interface InvoiceMetrics {
  automation_rate: number;
  avg_confidence: number;
  total: number;
  rule_count: number;
  aito_count: number;
  review_count: number;
}

export interface InvoicesResponse {
  invoices: InvoicePrediction[];
  metrics: InvoiceMetrics;
}

export interface AitoPanelConfig {
  operation: string;
  stats: { value: string; label: string }[];
  description: string;
  query: string;
  links: { label: string; url: string }[];
}
