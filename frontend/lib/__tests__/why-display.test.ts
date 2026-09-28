import { test } from "node:test";
import assert from "node:assert/strict";
import { isHiddenInPresentation } from "../why-display.ts";

const pattern = (...propositions: { field: string; value: string }[]) =>
  ({ type: "pattern" as const, lift: 3, propositions });

test("a vendor pattern is shown", () => {
  assert.equal(isHiddenInPresentation(pattern({ field: "vendor", value: "Kardex Finland Oy" })), false);
});

test("a category pattern is hidden, since category restates the account", () => {
  assert.equal(isHiddenInPresentation(pattern({ field: "category", value: "logistics" })), true);
});

test("a conjunction containing category is hidden whole", () => {
  assert.equal(isHiddenInPresentation(pattern(
    { field: "vendor", value: "Kardex Finland Oy" },
    { field: "category", value: "logistics" },
  )), true);
});

test("the raw amount is hidden, including through the invoice link", () => {
  assert.equal(isHiddenInPresentation(pattern({ field: "amount", value: "10209.0" })), true);
  assert.equal(isHiddenInPresentation(pattern({ field: "invoice_id.amount", value: "5966.97" })), true);
});

test("the amount band is a reusable pattern and stays", () => {
  assert.equal(isHiddenInPresentation(pattern({ field: "amount_band", value: "medium" })), false);
});

test("a pure-number description token is hidden, a word is not", () => {
  assert.equal(isHiddenInPresentation(pattern({ field: "description", value: "3493" })), true);
  assert.equal(isHiddenInPresentation(pattern({ field: "description", value: "fuel" })), false);
});

test("a legacy flat factor is judged by its field", () => {
  assert.equal(isHiddenInPresentation({ field: "category", value: "cloud", lift: 2 }), true);
});

test("the base rate has no propositions and is never hidden", () => {
  assert.equal(isHiddenInPresentation({ type: "base", base_p: 0.2 }), false);
});
