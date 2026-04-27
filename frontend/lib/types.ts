export interface InvoicePrediction {
  invoice_id: string;
  vendor: string;
  vendor_country?: string;
  category?: string;
  description?: string;
  amount: number;
  invoice_date?: string;
  due_days?: number;
  vat_pct?: number;
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
  type?: "base" | string;
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

export interface AitoPanelStat {
  value: string;
  label: string;
}

export interface AitoFlowStep {
  /** Step number shown in the tour badge */
  n: number;
  /** Short description: what does this Aito call produce on the page */
  produces: string;
  /** Aito API call summary, e.g. "_predict gl_code WHERE customer_id, vendor" */
  call: string;
}

export interface AitoPanelConfig {
  operation: string;
  stats: AitoPanelStat[];
  description: string;
  query: string;
  links: { label: string; url: string }[];
  /** Optional: ordered narrative of which Aito calls produce which UI parts */
  flow_steps?: AitoFlowStep[];
}
