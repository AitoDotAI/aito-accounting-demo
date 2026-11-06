// Which tenant does a page ask for first?
//
// `/matching/?customer_id=CUST-0127` used to request CUST-0001's pairs (and,
// since explain-on-demand, its first explanation) before the customer context
// had read the URL, then CUST-0127's: a wasted live Aito query per load. This
// loads the BUILT frontend in a real browser, answers every /api call with a
// stub, and records which customer each request names. No backend, no Aito.
//
// Needs a built `out/` (`npx next build`) and a Chrome/Chromium: CHROMIUM_PATH,
// else google-chrome / chromium on PATH (the only kind that runs on NixOS), else
// the newest Playwright download under ~/.cache/ms-playwright.
//
//   node --test e2e/first-fetch.test.ts

import { test } from "node:test";
import assert from "node:assert/strict";
import { chromium } from "playwright-core";
import { chromiumPath, serveOut } from "./helpers.ts";

const STUBS: Record<string, unknown> = {
  "/api/customers": { customers: [] },
  "/api/demo/today": { date: "2026-11-01" },
  "/api/matching/pairs": { pairs: [], metrics: { matched: 0, suggested: 0, unmatched: 0, total: 0,
    matched_by_aito: 0, matched_by_reference: 0, avg_confidence: 0, match_rate: 0 } },
};

async function load(url: string): Promise<{ asked: string[]; errors: string[] }> {
  const server = serveOut().listen(0);
  const port = (server.address() as { port: number }).port;
  const browser = await chromium.launch({ executablePath: chromiumPath() });
  try {
    const page = await (await browser.newContext()).newPage();   // empty localStorage
    const asked: string[] = [];
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
    await page.route("**/api/**", async (route) => {
      const u = new URL(route.request().url());
      const customer = u.searchParams.get("customer_id");
      if (customer) asked.push(customer);
      await route.fulfill({ status: 200, contentType: "application/json",
        body: JSON.stringify(STUBS[u.pathname] ?? {}) });
    });
    await page.goto(`http://localhost:${port}${url}`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(500);
    return { asked, errors };
  } finally {
    await browser.close();
    server.close();
  }
}

test("a URL that names a customer never makes the default tenant's requests", async () => {
  const { asked } = await load("/matching/?customer_id=CUST-0127");

  assert.ok(asked.length > 0, "the page made no customer-scoped request at all");
  assert.deepEqual([...new Set(asked)], ["CUST-0127"], `requested: ${asked.join(", ")}`);
});

test("with no customer in the URL the default tenant is still the one asked for", async () => {
  const { asked } = await load("/matching/");

  assert.deepEqual([...new Set(asked)], ["CUST-0001"], `requested: ${asked.join(", ")}`);
});

test("resolving the customer before the first render does not break hydration", async () => {
  // The built page is prerendered with the default tenant; a client that
  // renders a different one first must not trip React's hydration check.
  const { errors } = await load("/matching/?customer_id=CUST-0127");

  assert.deepEqual(errors, []);
});

// Every page that fetches data for the customer, not only matching.
const PAGES = [
  "/invoices/", "/matching/", "/anomalies/", "/formfill/", "/rulemining/", "/integrations/",
  "/quality/overview/", "/quality/predictions/", "/quality/evaluations/",
  "/quality/overrides/", "/quality/rules/",
];

for (const path of PAGES) {
  test(`${path} with a customer in the URL never asks for the default tenant`, async () => {
    const { asked } = await load(`${path}?customer_id=CUST-0127`);

    assert.ok(!asked.includes("CUST-0001"), `requested: ${asked.join(", ")}`);
  });
}
