// What a page keeps when the customer changes.
//
// Smart Form Fill held every tenant-scoped piece of state (the typed and
// preloaded form values, the predictions, the vendor list, the example
// templates) across a customer switch, so the previous tenant's vendor name
// and predictions stayed on screen under the new one, and with an emptied form
// the previous tenant's top template was preloaded and sent to the new
// tenant's endpoints. The built frontend is loaded in a real Chrome with every
// /api call stubbed; no backend, no Aito.
//
//   node --test e2e/tenant-switch.test.ts

import { test } from "node:test";
import assert from "node:assert/strict";
import { chromium, type Page } from "playwright-core";
import { chromiumPath, serveOut } from "./helpers.ts";

const A = "CUST-0127";
const B = "CUST-0100";
const A_VENDOR = "VENDOR-OF-A-ONLY";

const FIELDS = { gl_code: "4400", gl_label: "Supplies", approver: "EMP-A", approver_name: "A Approver",
  cost_centre: "CC-1", vat_pct: "25.5", payment_method: "SEPA", due_days: 30, category: "supplies" };

function stub(path: string, customer: string | null, body: unknown, calls: string[]): unknown {
  calls.push(`${path} ${customer ?? ""} ${typeof body === "string" ? body : ""}`.trim());
  if (path === "/api/formfill/templates") {
    return { templates: customer === A ? [{ vendor: A_VENDOR, match_count: 9, total_history: 10, confidence: 0.9, fields: FIELDS }] : [] };
  }
  if (path === "/api/formfill/vendors") return { vendors: customer === A ? [A_VENDOR] : ["VENDOR-OF-B"] };
  if (path === "/api/formfill/template") return { vendor: A_VENDOR, match_count: 9, total_history: 10, confidence: 0.9, fields: FIELDS };
  if (path === "/api/formfill/predict") {
    return { fields: [{ field: "gl_code", label: "GL code", value: "4400", raw_value: "4400", confidence: 0.9, alternatives: [], why: [] }] };
  }
  if (path === "/api/customers") return { customers: [] };
  if (path === "/api/demo/today") return { date: "2026-11-01" };
  return {};
}

async function openFormFillAndSwitch(clearFirst = false): Promise<{ page: Page; calls: string[]; close: () => Promise<void> }> {
  const server = serveOut().listen(0);
  const port = (server.address() as { port: number }).port;
  const browser = await chromium.launch({ executablePath: chromiumPath() });
  const page = await (await browser.newContext()).newPage();
  const calls: string[] = [];
  await page.route("**/api/**", async (route) => {
    const u = new URL(route.request().url());
    const post = route.request().postData() ?? null;
    await route.fulfill({ status: 200, contentType: "application/json",
      body: JSON.stringify(stub(u.pathname, u.searchParams.get("customer_id") ?? (post ? JSON.parse(post).customer_id : null),
        post ?? u.search, calls)) });
  });
  await page.goto(`http://localhost:${port}/formfill/?customer_id=${A}`);
  await page.waitForLoadState("networkidle");
  await page.waitForFunction((v) => (document.querySelector("input[placeholder='Type or select vendor']") as HTMLInputElement | null)?.value === v,
    A_VENDOR, { timeout: 10000 });
  if (clearFirst) {
    await page.click("button:has-text('Clear')");
    await page.waitForTimeout(300);
  }
  // The customer changes in place, as it does from the picker.
  await page.evaluate((id) => {
    const url = new URL(window.location.href);
    url.searchParams.set("customer_id", id);
    window.history.pushState({}, "", url.toString());
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, B);
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(800);
  return { page, calls, close: async () => { await browser.close(); server.close(); } };
}

test("the previous tenant's vendor is not left in the form after a customer switch", async () => {
  const { page, close } = await openFormFillAndSwitch();
  try {
    const vendor = await page.inputValue("input[placeholder='Type or select vendor']");
    assert.notEqual(vendor, A_VENDOR, `${A}'s vendor is still shown for ${B}`);
    assert.equal(vendor, "", "the form was not reset for the new customer");
  } finally { await close(); }
});

test("the previous tenant's vendor is never sent to the new tenant's endpoints", async () => {
  // With the form emptied first, the old example template is what the page
  // would preload for the new customer.
  const { calls, close } = await openFormFillAndSwitch(true);
  try {
    const leaked = calls.filter((c) => c.includes(B) && c.includes(A_VENDOR));
    assert.deepEqual(leaked, [], `sent ${A}'s vendor for ${B}: ${leaked.join(" | ")}`);
  } finally { await close(); }
});
