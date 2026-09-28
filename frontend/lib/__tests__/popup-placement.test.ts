// Run: node --test frontend/lib/__tests__/popup-placement.test.ts
// The why-popup opened ABOVE its button unconditionally, so on any row in
// the upper part of the screen its top ran off the viewport.
import { test } from "node:test";
import assert from "node:assert/strict";
import { placePopup } from "../popup-placement.ts";

const VIEW = { width: 1400, height: 900 };
const anchor = (top: number) => ({ top, bottom: top + 20, left: 600, width: 20 });

test("opens above when there is room above", () => {
  const p = placePopup(anchor(700), { width: 380, height: 400 }, VIEW);
  assert.equal(p.placement, "above");
  assert.ok(p.top >= 12, `top ${p.top} escapes the viewport`);
  assert.equal(p.maxHeight, undefined);
});

test("opens BELOW when the button is near the top", () => {
  const p = placePopup(anchor(120), { width: 380, height: 400 }, VIEW);
  assert.equal(p.placement, "below");
  assert.ok(p.top >= 12);
  assert.ok(p.top + 400 <= VIEW.height - 12);
});

test("never leaves the viewport: too tall for either side scrolls inside", () => {
  const p = placePopup(anchor(450), { width: 380, height: 1200 }, VIEW);
  assert.ok(p.top >= 12, `top ${p.top}`);
  assert.ok(p.maxHeight !== undefined && p.top + p.maxHeight <= VIEW.height - 12);
});

test("stays inside horizontally near the right edge", () => {
  const p = placePopup({ top: 700, bottom: 720, left: 1390, width: 10 }, { width: 380, height: 300 }, VIEW);
  assert.ok(p.left >= 12 && p.left + 380 <= VIEW.width - 12, `left ${p.left}`);
});

test("the arrow points at the button even when the popup is clamped", () => {
  // Button near the right edge: the popup shifts left, the arrow must not.
  const a = { top: 700, bottom: 720, left: 1300, width: 20 };
  const p = placePopup(a, { width: 380, height: 300 }, VIEW);
  assert.ok(p.left < 1310 - 190, "precondition: the popup really was shifted");
  assert.equal(p.left + p.arrowX, 1310, "arrow must sit over the button's centre");
});
