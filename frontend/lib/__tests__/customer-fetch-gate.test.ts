// Nothing under app/ or components/ may fetch for a customer from a bare
// effect: the fetch has to be inside `useCustomerEffect`, which waits for the
// customer context to have read the URL (lib/use-customer-effect.ts). A bare
// effect runs on the first render, when `customerId` is only the default, and
// asks for CUST-0001's data before the URL's customer is known.
//
// Reads the syntax tree. An effect is a call to useEffect / useLayoutEffect /
// useInsertionEffect (bare or as React.useEffect) whose callback is inline or a
// named function in the same file. A violation is a call to apiFetch/fetch in
// that callback whose first argument mentions `customer_id`, directly or through
// a `const` it names.
//
// Limits, so nobody reads this as stronger than it is:
//   - a fetch made by a HELPER that the effect calls is not seen (the formfill
//     page's effect-triggered fetchTemplate is one);
//   - a wrapper around apiFetch/fetch under another name is not seen;
//   - only app/ and components/ are scanned, not lib/;
//   - a customer id built any way that never spells `customer_id` is not seen.
// e2e/first-fetch.test.ts is the behavioural check that catches what this misses
// on the pages it loads.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const EFFECTS = new Set(["useEffect", "useLayoutEffect", "useInsertionEffect"]);
const FETCHES = new Set(["apiFetch", "fetch"]);

const calleeName = (node: ts.CallExpression): string =>
  ts.isIdentifier(node.expression) ? node.expression.text
    : ts.isPropertyAccessExpression(node.expression) ? node.expression.name.text : "";

export function fetchesFromBareEffect(source: string, name = "snippet.tsx"): string[] {
  const file = ts.createSourceFile(name, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);

  // name -> the initializers / function bodies it is declared with, anywhere in the file
  const declared = new Map<string, ts.Node[]>();
  const note = (id: string, node: ts.Node) => declared.set(id, [...(declared.get(id) ?? []), node]);
  const collect = (node: ts.Node) => {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer) note(node.name.text, node.initializer);
    if (ts.isFunctionDeclaration(node) && node.name) note(node.name.text, node);
    ts.forEachChild(node, collect);
  };
  collect(file);

  const mentionsCustomer = (expr: ts.Node | undefined, depth = 0): boolean => {
    if (!expr) return false;
    if (expr.getText(file).includes("customer_id")) return true;
    if (ts.isIdentifier(expr) && depth < 3) {
      return (declared.get(expr.text) ?? []).some((init) => mentionsCustomer(init, depth + 1));
    }
    return false;
  };

  const found: string[] = [];
  const scan = (body: ts.Node) => {
    const visit = (node: ts.Node) => {
      if (ts.isCallExpression(node) && FETCHES.has(calleeName(node)) && mentionsCustomer(node.arguments[0])) {
        found.push(`${calleeName(node)}:${file.getLineAndCharacterOfPosition(node.getStart(file)).line + 1}`);
      }
      ts.forEachChild(node, visit);
    };
    visit(body);
  };

  const visitFile = (node: ts.Node) => {
    if (ts.isCallExpression(node) && EFFECTS.has(calleeName(node)) && node.arguments[0]) {
      const callback = node.arguments[0];
      if (ts.isIdentifier(callback)) (declared.get(callback.text) ?? []).forEach(scan);
      else scan(callback);
    }
    ts.forEachChild(node, visitFile);
  };
  visitFile(file);
  return found;
}

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return entry === "node_modules" ? [] : sources(path);
    return path.endsWith(".tsx") || path.endsWith(".ts") ? [path] : [];
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

// ── Shapes a text match on the first argument misses (CPO review of #78) ──

const effectShapes: Record<string, string> = {
  "the url in a const first": `
    export default function P() {
      useEffect(() => {
        const url = \`/api/x?customer_id=\${customerId}\`;
        apiFetch(url);
      }, [customerId]);
    }`,
  "useLayoutEffect": `
    export default function P() {
      useLayoutEffect(() => { apiFetch(\`/api/x?customer_id=\${customerId}\`); }, [customerId]);
    }`,
  "React.useEffect": `
    export default function P() {
      React.useEffect(() => { apiFetch(\`/api/x?customer_id=\${customerId}\`); }, [customerId]);
    }`,
  "a named effect function (const)": `
    export default function P() {
      const load = () => { apiFetch(\`/api/x?customer_id=\${customerId}\`); };
      useEffect(load, [customerId]);
    }`,
  "a named effect function (declaration)": `
    export default function P() {
      function load() { apiFetch(\`/api/x?customer_id=\${customerId}\`); }
      useEffect(load, [customerId]);
    }`,
};

for (const [name, source] of Object.entries(effectShapes)) {
  test(`a bare effect is found when it uses ${name}`, () => {
    assert.equal(fetchesFromBareEffect(source).length, 1);
  });
}

test("the same shapes inside useCustomerEffect are accepted", () => {
  const fine = `
    export default function P() {
      useCustomerEffect(() => {
        const url = \`/api/x?customer_id=\${customerId}\`;
        apiFetch(url);
      }, [customerId]);
    }`;
  assert.deepEqual(fetchesFromBareEffect(fine), []);
});

test("no page or component fetches for a customer from a bare effect", () => {
  const problems = ["app", "components"].flatMap((dir) =>
    sources(join(ROOT, dir)).flatMap((path) =>
      fetchesFromBareEffect(readFileSync(path, "utf8"), path)
        .map((hit) => `${relative(ROOT, path)} ${hit}`)));

  assert.deepEqual(problems, [],
    "use useCustomerEffect (lib/use-customer-effect.ts) so the fetch waits for the customer");
});
