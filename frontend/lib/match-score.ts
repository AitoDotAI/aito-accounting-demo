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
}

export function shownMatchScore(pair: ScoredPair): number | null {
  if (pair.matched_by === "reference") return null;
  // A same-vendor substitute carries no explanation: Aito ranked a different
  // invoice, so its probability belongs to that one, not to this match.
  if (!pair.explanation || pair.explanation.length === 0 || pair.model_p == null) return pair.confidence;
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
