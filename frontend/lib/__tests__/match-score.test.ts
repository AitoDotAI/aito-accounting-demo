import { test } from "node:test";
import assert from "node:assert/strict";
import { averageExplainedScore, shownMatchScore } from "../match-score.ts";

const base = { model_p: 0.405, confidence: 0.70, matched_by: "aito" as const };
const why = [{ type: "base" as const, base_p: 0.00003 }];

test("an Aito match shows the probability its explanation adds up to, not a blend", () => {
  // Measured live, CUST-0000 TXN-000005: the badge said 0.70 while the
  // explanation ended at 41% (0.5 x 0.405 + 0.5 x an amount score).
  assert.equal(shownMatchScore({ ...base, explanation: why }), 0.405);
});

test("a same-vendor substitute has no explanation, so it keeps its own score", () => {
  assert.equal(shownMatchScore({ ...base, explanation: undefined }), 0.70);
});

test("a reference lookup shows no model score", () => {
  assert.equal(shownMatchScore({ ...base, matched_by: "reference", explanation: undefined }), null);
});

test("the average card averages what the badges show for Aito's matches", () => {
  const pairs = [
    { ...base, explanation: why },
    { ...base, model_p: 0.9, explanation: why },
    { ...base, matched_by: "reference" as const, explanation: undefined },
  ];
  assert.equal(averageExplainedScore(pairs), (0.405 + 0.9) / 2);
});

// ── The live page ships no explanation in the list ─────────────────────
//
// Since matching asks Aito for the explanation only for the expanded row, a
// live pair has `explanation: []` until its row opens. The badge must not
// depend on that: it showed the 0.83 blend beside a chain that adds up to
// 71%, and the average card showed the blend's mean (0.82, not 0.65). Seen in
// the browser on a local Aito (CUST-0127), 2026-11-06.

test("a live pair with no explanation yet still shows Aito's probability", () => {
  assert.equal(shownMatchScore({ ...base, explanation: [], substituted: false }), 0.405);
});

test("a substitute keeps its own score, explanation or not", () => {
  assert.equal(shownMatchScore({ ...base, explanation: [], substituted: true }), 0.70);
  assert.equal(shownMatchScore({ ...base, explanation: why, substituted: true }), 0.70);
});

test("a payload from before the substituted flag falls back to the old rule", () => {
  assert.equal(shownMatchScore({ ...base, explanation: [] }), 0.70);
  assert.equal(shownMatchScore({ ...base, explanation: why }), 0.405);
});

test("the average card does not wait for the explanations to arrive", () => {
  const pairs = [
    { ...base, explanation: [], substituted: false },
    { ...base, model_p: 0.9, explanation: [], substituted: false },
  ];
  assert.equal(averageExplainedScore(pairs), (0.405 + 0.9) / 2);
});
