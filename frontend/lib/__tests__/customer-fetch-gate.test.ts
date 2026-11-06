// Nothing under app/ or components/ may fetch for a customer from a bare
// `useEffect`: the fetch has to be inside `useCustomerEffect`, which waits for
// the customer context to have read the URL (lib/use-customer-effect.ts).
// A bare effect runs on the first render, when `customerId` is only the
// default, and asks for CUST-0001's data before the URL's customer is known.
//
// Reads the syntax tree: a call to apiFetch/fetch whose first argument mentions
// `customer_id`, with a `useEffect(...)` call among its ancestors. Known limit:
// a fetch made by a helper function that an effect then calls is not seen.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

export function fetchesFromBareEffect(source: string, name = "snippet.tsx"): string[] {
  const file = ts.createSourceFile(name, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const found: string[] = [];
  const callee = (node: ts.CallExpression) =>
    ts.isIdentifier(node.expression) ? node.expression.text : "";

  const visit = (node: ts.Node, inBareEffect: boolean) => {
    let inside = inBareEffect;
    if (ts.isCallExpression(node)) {
      const name = callee(node);
      if (name === "useEffect") inside = true;
      if ((name === "apiFetch" || name === "fetch") && inside && node.arguments[0]
          && node.arguments[0].getText(file).includes("customer_id")) {
        const { line } = file.getLineAndCharacterOfPosition(node.getStart(file));
        found.push(`${name}:${line + 1}`);
      }
    }
    ts.forEachChild(node, (child) => visit(child, inside));
  };
  visit(file, false);
  return found;
}

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return entry === "node_modules" ? [] : sources(path);
    return path.endsWith(".tsx") ? [path] : [];
  });
}

test("a bare useEffect that fetches for a customer is found", () => {
  const bare = `
    export default function P() {
      const { customerId } = useCustomer();
      useEffect(() => { apiFetch(\`/api/x?customer_id=\${customerId}\`); }, [customerId]);
    }`;
  assert.equal(fetchesFromBareEffect(bare).length, 1);
});

test("a fetch inside useCustomerEffect, a handler, or without a customer is accepted", () => {
  const fine = `
    export default function P() {
      const { customerId } = useCustomer();
      useCustomerEffect(() => { apiFetch(\`/api/x?customer_id=\${customerId}\`); }, [customerId]);
      const onClick = () => apiFetch(\`/api/y?customer_id=\${customerId}\`);
      useEffect(() => { apiFetch("/api/quality/domains"); }, []);
    }`;
  assert.deepEqual(fetchesFromBareEffect(fine), []);
});

test("no page or component fetches for a customer from a bare useEffect", () => {
  const problems = ["app", "components"].flatMap((dir) =>
    sources(join(ROOT, dir)).flatMap((path) =>
      fetchesFromBareEffect(readFileSync(path, "utf8"), path)
        .map((hit) => `${relative(ROOT, path)} ${hit}`)));

  assert.deepEqual(problems, [],
    "use useCustomerEffect (lib/use-customer-effect.ts) so the fetch waits for the customer");
});
