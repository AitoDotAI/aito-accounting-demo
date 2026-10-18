// Readable text for the priors Aito reports through linked rows (ADR 0031).
//
// A linkedPrior is what a lift was SMOOTHED TOWARD, not part of the
// evidence: it is not a term in $p (core, from the 2.11.6 code). So it is
// worded "smoothed toward ...", never "because ...", and shown without a
// multiplier.
//
// The backend keeps each lift's `linkedPrior` as priors: [{field, value, lift}].
// - Input side: a path through a link in the query, such as
//   `vendor_business_id.industry`. What the vendor is, from the PRH register.
// - Target side: a bare column of the predicted row, such as `department`.
//   What the predicted person (or account) is.

export interface LinkedPrior {
  field: string;
  value: string;
  lift: number;
}

const LINK_NOUNS: Record<string, string> = {
  vendor_business_id: "vendor",
  approver: "approver",
  processor: "processor",
};

/** Lifts within this of 1 say nothing either way, as elsewhere in the panel. */
const MATERIAL = 1.05;

export function priorLabel(field: string): string {
  const [link, ...rest] = field.split(".");
  if (rest.length === 0) return field.replace(/_/g, " ");
  const noun = LINK_NOUNS[link] ?? link.replace(/_/g, " ");
  return `${noun}'s ${rest.join(" ").replace(/_/g, " ")}`;
}

function isTargetSide(prior: LinkedPrior): boolean {
  return !prior.field.includes(".");
}

/** A code is redundant next to its own name ("industry_code" beside "industry"). */
function withoutRedundantCodes(priors: LinkedPrior[]): LinkedPrior[] {
  const fields = new Set(priors.map((p) => p.field));
  return priors.filter((p) => !(p.field.endsWith("_code") && fields.has(p.field.slice(0, -"_code".length))));
}

/** "smoothed toward ..." lines for one pattern, for its linked input rows. */
export function smoothedTowardLines(priors: LinkedPrior[] = []): string[] {
  return withoutRedundantCodes(priors.filter((p) => !isTargetSide(p) && p.lift >= MATERIAL))
    .map((p) => {
      const [link, ...rest] = p.field.split(".");
      const noun = LINK_NOUNS[link] ?? link.replace(/_/g, " ");
      return `smoothed toward ${noun}s whose ${rest.join(" ").replace(/_/g, " ")} is ${p.value}`;
    });
}

/** The groups the predicted value's estimate was smoothed toward (target-side priors): one per field, strongest first. */
export function targetProfile(patterns: { priors?: LinkedPrior[] }[]): LinkedPrior[] {
  const best = new Map<string, LinkedPrior>();
  for (const prior of patterns.flatMap((p) => p.priors ?? [])) {
    if (!isTargetSide(prior) || prior.lift < MATERIAL) continue;
    const seen = best.get(prior.field);
    if (!seen || prior.lift > seen.lift) best.set(prior.field, prior);
  }
  return [...best.values()].sort((a, b) => b.lift - a.lift);
}
