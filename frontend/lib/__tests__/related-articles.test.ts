import { test } from "node:test";
import assert from "node:assert/strict";
import { withClickEvidence } from "../related-articles.ts";

const article = (article_id: string, supporting_clicks?: number) => ({ article_id, supporting_clicks });

test("an article someone read next is listed", () => {
  assert.deepEqual(withClickEvidence([article("APP-06", 3)]).map((a) => a.article_id), ["APP-06"]);
});

test("an article with no supporting clicks is not listed, however high Aito ranked it", () => {
  assert.deepEqual(withClickEvidence([article("LEGAL-07", 0), article("APP-06", 1)]).map((a) => a.article_id), ["APP-06"]);
});

test("an answer that does not report clicks is treated as having none", () => {
  assert.deepEqual(withClickEvidence([article("APP-06")]), []);
});
