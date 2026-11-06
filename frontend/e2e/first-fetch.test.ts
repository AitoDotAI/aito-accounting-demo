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
import { createServer } from "node:http";
import { readFileSync, existsSync, readdirSync, statSync } from "node:fs";
import { dirname, extname, join, resolve } from "node:path";
import { homedir } from "node:os";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const OUT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "out");
const TYPES: Record<string, string> = {
  ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json",
  ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".woff2": "font/woff2", ".txt": "text/plain",
};

function chromiumPath(): string {
  if (process.env.CHROMIUM_PATH) return process.env.CHROMIUM_PATH;
  for (const dir of (process.env.PATH ?? "").split(":")) {
    for (const name of ["google-chrome-stable", "google-chrome", "chromium", "chromium-browser"]) {
      if (dir && existsSync(join(dir, name))) return join(dir, name);
    }
  }
  const root = join(homedir(), ".cache", "ms-playwright");
  const dirs = existsSync(root) ? readdirSync(root).filter((d) => /^chromium-\d+$/.test(d))
    .sort((a, b) => Number(b.split("-")[1]) - Number(a.split("-")[1])) : [];
  for (const d of dirs) {
    for (const sub of ["chrome-linux64", "chrome-linux"]) {
      const candidate = join(root, d, sub, "chrome");
      if (existsSync(candidate)) return candidate;
    }
  }
  throw new Error("no Chrome/Chromium found: set CHROMIUM_PATH");
}

function serveOut() {
  return createServer((req, res) => {
    const path = decodeURIComponent((req.url ?? "/").split("?")[0]);
    let file = join(OUT, path);
    if (existsSync(file) && statSync(file).isDirectory()) file = join(file, "index.html");
    if (!existsSync(file)) file = join(OUT, path + ".html");
    if (!existsSync(file)) { res.writeHead(404); res.end("not found"); return; }
    res.writeHead(200, { "content-type": TYPES[extname(file)] ?? "application/octet-stream" });
    res.end(readFileSync(file));
  });
}

const STUBS: Record<string, unknown> = {
  "/api/customers": { customers: [] },
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
