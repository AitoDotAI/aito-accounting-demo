// "Users who read this also read" is a claim about clicks, so it lists only
// articles someone actually opened next. Aito's ranking alone is not enough:
// `_recommend` on a link target can put a candidate with no supporting
// clicks first, at a $p of about 0.998 (engine issue td-20261001174213737932).

export interface RelatedArticle {
  article_id: string;
  /** How often this customer's users opened it right after the current article. */
  supporting_clicks?: number;
}

export function withClickEvidence<T extends RelatedArticle>(articles: T[]): T[] {
  return articles.filter((a) => (a.supporting_clicks ?? 0) >= 1);
}
