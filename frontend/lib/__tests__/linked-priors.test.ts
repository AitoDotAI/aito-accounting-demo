import { test } from "node:test";
import assert from "node:assert/strict";
import { priorLabel, smoothedTowardLines, targetProfile } from "../linked-priors.ts";

// Shapes as the backend emits them from Aito 2.11.6's linkedPrior.
const industry = { field: "vendor_business_id.industry", value: "Computer programming activities", lift: 4.16 };
const industryCode = { field: "vendor_business_id.industry_code", value: "62100", lift: 4.09 };
const department = { field: "department", value: "Procurement", lift: 4.35 };
const role = { field: "role", value: "Manager", lift: 1.88 };

test("a path through a link reads as the linked thing's property", () => {
  assert.equal(priorLabel("vendor_business_id.industry"), "vendor's industry");
  assert.equal(priorLabel("vendor_business_id.city"), "vendor's city");
});

test("an input-side prior reads as what the lift was smoothed toward, not as a reason", () => {
  // Core, from the 2.11.6 code: a linkedPrior is the smoothing target, not
  // a multiplicative term in $p. "because ..." would claim evidence.
  assert.deepEqual(smoothedTowardLines([industry, industryCode]),
    ["smoothed toward vendors whose industry is Computer programming activities"]);
});

test("target-side priors are not input lines: they describe the predicted value", () => {
  assert.deepEqual(smoothedTowardLines([department, role]), []);
});

test("the predicted person's profile collects target-side priors once, strongest first", () => {
  const patterns = [{ priors: [department, role] }, { priors: [{ ...department, lift: 3.9 }, industry] }];
  assert.deepEqual(targetProfile(patterns).map((p) => [p.field, p.value]), [["department", "Procurement"], ["role", "Manager"]]);
});

test("a prior that lowers the value is not offered as a reason", () => {
  assert.deepEqual(targetProfile([{ priors: [{ ...role, lift: 0.6 }] }]), []);
});
