// Shared by the e2e tests: serve the BUILT frontend (`out/`) and find a Chrome.
import { createServer } from "node:http";
import { readFileSync, existsSync, readdirSync, statSync } from "node:fs";
import { dirname, extname, join, resolve } from "node:path";
import { homedir } from "node:os";
import { fileURLToPath } from "node:url";

const OUT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "out");
const TYPES: Record<string, string> = {
  ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json",
  ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".woff2": "font/woff2", ".txt": "text/plain",
};

export function chromiumPath(): string {
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

export function serveOut() {
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
