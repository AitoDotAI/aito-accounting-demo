// What Smart Form Fill keeps, and sends, when the customer changes.
//
// The page held every tenant-scoped piece of state across a customer switch,
// sent every /api/formfill/predict as the DEFAULT customer (a useCallback with
// no dependencies kept the first render's customerId), and let a template or
// example list that was still in flight for the previous customer land on the
// new one. The built frontend is loaded in a real Chrome with every /api call
// stubbed (no backend, no Aito). The stubs echo the customer they were asked
// for, so a leak shows up as another tenant's name on screen, and a response
// can be HELD until after the switch, which an instant stub cannot show.
//
//   node --test e2e/tenant-switch.test.ts

import { test } from "node:test";
import assert from "node:assert/strict";
import { chromium, type Page } from "playwright-core";
import { chromiumPath, serveOut } from "./helpers.ts";

const A = "CUST-0127";
const B = "CUST-0100";
const A_VENDOR = "VENDOR-OF-A-ONLY";
const VENDOR_INPUT = "input[placeholder='Type or select vendor']";

interface Call { path: string; customer: string | null; vendor: string | null }

const fields = (customer: string) => ({
  gl_code: "4400", gl_label: `GL-LABEL-OF-${customer}`, approver: `APPROVER-OF-${customer}`,
  approver_name: `APPROVER-OF-${customer}`, cost_centre: "CC-1", vat_pct: "25.5",
  payment_method: "SEPA", due_days: 30, category: "supplies",
});

function answer(path: string, customer: string | null, vendor: string | null): unknown {
  switch (path) {
    case "/api/formfill/templates":
      return { templates: customer === A
        ? [{ vendor: A_VENDOR, match_count: 9, total_history: 10, confidence: 0.9, fields: fields(A) }] : [] };
    case "/api/formfill/vendors":
      return { vendors: [customer === A ? A_VENDOR : "VENDOR-OF-B"] };
    case "/api/formfill/template":
      return { vendor, match_count: 9, total_history: 10, confidence: 0.9, fields: fields(customer ?? "NONE") };
    case "/api/formfill/predict":
      return { fields: [{ field: "gl_code", label: "GL code", value: `PREDICTED-FOR-${customer}`,
        raw_value: "4400", confidence: 0.9, predicted: true, alternatives: [] }] };
    case "/api/formfill/log":
      return { logged: 3 };
    case "/api/customers": return { customers: [] };
    case "/api/demo/today": return { date: "2026-11-01" };
    default: return {};
  }
}

interface Harness {
  page: Page;
  calls: Call[];
  /** Let go of an answer that `open({ hold })` is holding. */
  release: (path: string, customer: string) => void;
  switchTo: (customer: string) => Promise<void>;
  close: () => Promise<void>;
}

/** `hold`: answers to hold from the very first request, as [path, customer] pairs. */
async function open(opts: { hold?: [string, string][] } = {}, startAt: string = A): Promise<Harness> {
  const server = serveOut().listen(0);
  const port = (server.address() as { port: number }).port;
  const browser = await chromium.launch({ executablePath: chromiumPath() });
  const page = await (await browser.newContext()).newPage();
  const calls: Call[] = [];
  const holds = new Map<string, Promise<void>>();
  const releases = new Map<string, () => void>();
  for (const [path, customer] of opts.hold ?? []) {
    holds.set(`${path}|${customer}`, new Promise<void>((resolve) => { releases.set(`${path}|${customer}`, resolve); }));
  }
  await page.route("**/api/**", async (route) => {
    const u = new URL(route.request().url());
    const post = route.request().postData();
    const body = post ? JSON.parse(post) : null;
    const customer = u.searchParams.get("customer_id") ?? body?.customer_id ?? null;
    const vendor = u.searchParams.get("vendor") ?? body?.vendor ?? null;
    calls.push({ path: u.pathname, customer, vendor });
    const held = holds.get(`${u.pathname}|${customer}`);
    if (held) await held;
    await route.fulfill({ status: 200, contentType: "application/json",
      body: JSON.stringify(answer(u.pathname, customer, vendor)) });
  });
  await page.goto(`http://localhost:${port}/formfill/?customer_id=${startAt}`);
  return {
    page, calls,
    release: (path, customer) => releases.get(`${path}|${customer}`)?.(),
    switchTo: async (customer) => {
      // The customer changes in place, as it does from the picker.
      await page.evaluate((id) => {
        const url = new URL(window.location.href);
        url.searchParams.set("customer_id", id);
        window.history.pushState({}, "", url.toString());
        window.dispatchEvent(new PopStateEvent("popstate"));
      }, customer);
    },
    close: async () => { await browser.close(); server.close(); },
  };
}

const preloaded = (page: Page) => page.waitForFunction(
  ({ sel, v }) => (document.querySelector(sel) as HTMLInputElement | null)?.value === v,
  { sel: VENDOR_INPUT, v: A_VENDOR }, { timeout: 10000 });

const settle = async (page: Page) => { await page.waitForLoadState("networkidle"); await page.waitForTimeout(800); };

test("every prediction is asked for the selected customer, on load and after a switch", async () => {
  const h = await open();
  try {
    await preloaded(h.page);
    await settle(h.page);
    const initial = h.calls.filter((c) => c.path === "/api/formfill/predict");
    assert.ok(initial.length > 0, "no prediction was requested");
    assert.deepEqual([...new Set(initial.map((c) => c.customer))], [A],
      `predict asked for: ${initial.map((c) => c.customer).join(", ")}`);

    await h.switchTo(B);
    await settle(h.page);
    h.calls.length = 0;
    await h.page.fill(VENDOR_INPUT, "SOMETHING TYPED");
    await h.page.waitForTimeout(1200);
    const after = h.calls.filter((c) => c.path === "/api/formfill/predict");
    assert.ok(after.length > 0, "no prediction after the switch");
    assert.deepEqual([...new Set(after.map((c) => c.customer))], [B],
      `after the switch predict asked for: ${after.map((c) => c.customer).join(", ")}`);
  } finally { await h.close(); }
});

test("the previous tenant's vendor is not left in the form after a customer switch", async () => {
  const h = await open();
  try {
    await preloaded(h.page);
    await settle(h.page);
    await h.switchTo(B);
    await settle(h.page);
    assert.equal(await h.page.inputValue(VENDOR_INPUT), "", `${A}'s vendor is still shown for ${B}`);
  } finally { await h.close(); }
});

test("the previous tenant's vendor is never sent to the new tenant's endpoints", async () => {
  const h = await open();
  try {
    await preloaded(h.page);
    await settle(h.page);
    // With the form emptied first, the old example template is what the page
    // would preload for the new customer.
    await h.page.click("button:has-text('Clear')");
    await h.page.waitForTimeout(300);
    await h.switchTo(B);
    await settle(h.page);
    const leaked = h.calls.filter((c) => c.customer === B && c.vendor === A_VENDOR);
    assert.deepEqual(leaked, [], `sent ${A}'s vendor for ${B}: ${JSON.stringify(leaked)}`);
  } finally { await h.close(); }
});

test("a template still in flight for the previous customer does not land on the new one", async () => {
  const h = await open({ hold: [["/api/formfill/template", A]] });
  const release = () => h.release("/api/formfill/template", A);
  try {
    await preloaded(h.page);            // the preload asked for A's template; the answer is held
    await h.switchTo(B);
    await h.page.waitForTimeout(1000);   // not networkidle: the held request never idles
    release();
    await h.page.waitForTimeout(1000);
    const text = await h.page.innerText("body");
    assert.ok(!text.includes(`APPROVER-OF-${A}`), `${A}'s template is on ${B}'s page`);
    assert.equal(await h.page.locator("button:has-text('Apply template')").count(), 0,
      "an Apply template button offers the previous customer's routing");
  } finally { release(); await h.close(); }
});

test("the example templates in flight for the previous customer are not preloaded for the new one", async () => {
  const h = await open({ hold: [["/api/formfill/templates", A]] });
  const release = () => h.release("/api/formfill/templates", A);
  try {
    await h.page.waitForLoadState("domcontentloaded");
    await h.page.waitForTimeout(500);   // A's list is requested and held
    await h.switchTo(B);
    await h.page.waitForTimeout(1000);
    release();
    await h.page.waitForTimeout(1000);
    assert.equal(await h.page.inputValue(VENDOR_INPUT), "", `${A}'s example was preloaded for ${B}`);
    assert.deepEqual(h.calls.filter((c) => c.customer === B && c.vendor === A_VENDOR), []);
    // The late list must not be shown either: the quick-start cards print the
    // example's routing, and the vendor dropdown lists the vendors fetched for A.
    const text = await h.page.innerText("body");
    assert.ok(!text.includes(`APPROVER-OF-${A}`), `${A}'s example templates are on ${B}'s page`);
    assert.ok(!(await h.page.content()).includes(A_VENDOR), `${A}'s vendor is in ${B}'s page`);
  } finally { release(); await h.close(); }
});

test("a submission message does not follow the form to another customer", async () => {
  const h = await open();
  try {
    await preloaded(h.page);
    await settle(h.page);
    await h.page.click("button:has-text('Log submission')");
    await h.page.waitForSelector("text=Logged", { timeout: 5000 });
    await h.switchTo(B);
    await h.page.waitForTimeout(600);
    assert.equal(await h.page.locator("text=Logged").count(), 0, `${A}'s submission message is on ${B}'s page`);
  } finally { await h.close(); }
});
