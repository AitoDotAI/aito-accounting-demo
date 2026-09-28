import type { WhyFactor } from "./types";

/**
 * Which `$why` factors earn a card of their own outside developer view.
 *
 * Three kinds of factor are true but mislead an accountant reading the
 * explanation:
 *
 *  - `category`: the demo's category field is close to the account name,
 *    so "because category is logistics" reads as the answer restating
 *    itself rather than as a reason.
 *  - the raw `amount`: "amount is 10209.0" names one exact figure, which
 *    is a coincidence in the data, not a pattern a person would reuse.
 *  - pure-number tokens: an invoice number or a date fragment in the
 *    description ("fuel charges - 3493") matched by the text analyzer.
 *
 * Hidden factors are never dropped. WhyCards folds them into its single
 * "other signals" line, whose multiplier keeps `base × … = probability`
 * exact, and developer view shows every one.
 */
const FIELDS_HIDDEN_IN_PRESENTATION = new Set(["category", "amount"]);

const PURE_NUMBER = /^[\d\s.,:/-]+$/;

function stripLinkPrefix(field: string): string {
  return field.replace(/^invoice_id\./, "");
}

export function isHiddenInPresentation(factor: WhyFactor): boolean {
  // A conjunction is hidden whole if any part of it is: its lift belongs
  // to the combination, so showing the remaining parts with that lift
  // would credit them with evidence that was not theirs alone.
  const propositions = [
    ...(factor.propositions ?? []),
    ...(factor.field ? [{ field: factor.field, value: factor.value ?? "" }] : []),
  ];
  return propositions.some(
    (p) => FIELDS_HIDDEN_IN_PRESENTATION.has(stripLinkPrefix(p.field)) || PURE_NUMBER.test(p.value),
  );
}
