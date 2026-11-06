// The number a payment match shows is the one its explanation adds up to.
//
// The backend's `confidence` is a blend: 0.5 x Aito's probability + 0.5 x
// how closely the amounts agree. It decides matched / suggested, and it
// stays that way. But showing it beside Aito's explanation put two numbers
// on screen that never agreed (a 0.70 badge over a chain ending at 41%).
// The amount agreement is already shown in words ("overpaid EUR 1.00").

interface ScoredPair {
  matched_by: "reference" | "aito" | null;
  confidence: number;
  /** Aito's own probability for this invoice; the explanation decomposes this. */
  model_p?: number;
  explanation?: unknown[];
  /** True when the invoice is a same-vendor stand-in for the one Aito ranked. */
  substituted?: boolean;
}

export function shownMatchScore(pair: ScoredPair): number | null {
  if (pair.matched_by === "reference") return null;
  if (pair.model_p == null) return pair.confidence;
  // A same-vendor substitute: Aito ranked a different invoice, so its
  // probability belongs to that one, not to this match.
  if (pair.substituted === true) return pair.confidence;
  // The live list ships no explanation until a row is opened, so whether one
  // is present says nothing about which number is right. Payloads from before
  // the `substituted` flag are the exception, and keep the old rule.
  if (pair.substituted === undefined && !(pair.explanation && pair.explanation.length > 0)) {
    return pair.confidence;
  }
  return pair.model_p;
}

/** The "Avg Aito probability" card: the mean of what Aito's match badges show. */
export function averageExplainedScore(pairs: ScoredPair[]): number | null {
  const scores = pairs
    .filter((p) => p.matched_by === "aito")
    .map(shownMatchScore)
    .filter((s): s is number => s != null);
  return scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null;
}
