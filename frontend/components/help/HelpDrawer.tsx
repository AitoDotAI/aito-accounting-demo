"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { useCustomer } from "@/lib/customer-context";
import { apiFetch } from "@/lib/api";

interface Article {
  article_id: string;
  title: string;
  body: string;
  category: string;
  customer_id: string;
  tags?: string;
  page_context?: string;
}

interface HelpStats {
  impressions: number;
  clicks: number;
  ctr: number;
}

const CATEGORY_LABEL: Record<string, string> = {
  app: "Product docs",
  legal: "Legal & compliance",
  internal: "Internal guidance",
};

const CATEGORY_COLOR: Record<string, string> = {
  app: "var(--blue)",
  legal: "var(--gold-dark)",
  internal: "var(--green)",
};

/**
 * Floating ? button + slide-in help panel. Articles ranked by CTR
 * via Aito _predict; impression/click data feeds the next ranking.
 *
 * Same pattern as aito-demo's product recommendations: every shown
 * article is an impression, every click is a positive signal.
 */
export default function HelpDrawer() {
  const pathname = usePathname();
  const { customerId } = useCustomer();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [articles, setArticles] = useState<Article[]>([]);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [related, setRelated] = useState<Record<string, Article[]>>({});
  const [relatedLoading, setRelatedLoading] = useState<string | null>(null);
  const [stats, setStats] = useState<HelpStats | null>(null);
  // Track the last clicked article so impressions on next-loaded
  // articles can carry prev_article_id (matches the synthesised
  // session model in help_impressions).
  const lastClickedRef = useRef<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastImpressionPage = useRef<string>("");

  // Prefetch when the page or customer changes, so the server-side
  // cache is warm by the time the user actually clicks the "?"
  // button. Help search runs three sequential Aito calls (~3-12s
  // cold), warm cache hit is <5 ms.
  //
  // This effect runs both on prefetch (drawer closed) and on open --
  // when the drawer opens we also log impressions, which the
  // prefetch pass skips so we don't double-log.
  useEffect(() => {
    if (query) return;  // typed-query searches handled by the next effect
    let cancelled = false;
    setLoading(open);
    const url = `/api/help/search?customer_id=${encodeURIComponent(customerId)}&page=${encodeURIComponent(pathname || "")}&q=&limit=5`;
    apiFetch<{ articles: Article[] }>(url)
      .then((d) => {
        if (cancelled) return;
        setArticles(d.articles ?? []);
        // Only log impressions when the drawer is actually open
        // and the user is looking at this list.
        if (!open) return;
        const key = `${pathname}|${customerId}|`;
        if (key !== lastImpressionPage.current) {
          lastImpressionPage.current = key;
          for (const a of d.articles ?? []) {
            apiFetch("/api/help/impression", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                article_id: a.article_id,
                customer_id: customerId,
                page: pathname || "",
                query: "",
                clicked: false,
              }),
            }).catch(() => {});
          }
        }
      })
      .catch(() => { if (!cancelled) setArticles([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [pathname, customerId, open, query]);

  // Per-tenant deflection numbers: total impressions, clicks, CTR.
  // Fetched lazily on first open so closed-drawer page loads stay
  // cheap; refreshed when the customer changes.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setStats(null);
    apiFetch<HelpStats>(`/api/help/stats?customer_id=${encodeURIComponent(customerId)}`)
      .then((d) => { if (!cancelled) setStats(d); })
      .catch(() => { if (!cancelled) setStats(null); });
    return () => { cancelled = true; };
  }, [open, customerId]);

  // Typed-query searches: only when the drawer is open AND the user
  // typed something. Doesn't prefetch when closed (we'd be firing on
  // every keystroke).
  useEffect(() => {
    if (!open || !query) return;
    let cancelled = false;
    setLoading(true);
    const url = `/api/help/search?customer_id=${encodeURIComponent(customerId)}&page=${encodeURIComponent(pathname || "")}&q=${encodeURIComponent(query)}&limit=5`;
    apiFetch<{ articles: Article[] }>(url)
      .then((d) => { if (!cancelled) setArticles(d.articles ?? []); })
      .catch(() => { if (!cancelled) setArticles([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [open, pathname, customerId, query]);

  const onQueryChange = (v: string) => {
    setQuery(v);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      // Re-fetch happens via useEffect on `query`
    }, 250);
  };

  const onArticleClick = (a: Article) => {
    const opening = expanded !== a.article_id;
    setExpanded(opening ? a.article_id : null);

    // Log the click; carry prev_article_id if the user came from
    // another article in this session.
    apiFetch("/api/help/impression", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        article_id: a.article_id,
        customer_id: customerId,
        page: pathname || "",
        query,
        clicked: true,
        prev_article_id: lastClickedRef.current,
      }),
    }).catch(() => {});

    if (opening) {
      lastClickedRef.current = a.article_id;
      // Fetch related articles for the newly expanded one (cached
      // per article_id, so repeated open/close is cheap).
      if (!related[a.article_id]) {
        setRelatedLoading(a.article_id);
        apiFetch<{ articles: Article[] }>(
          `/api/help/related?article_id=${encodeURIComponent(a.article_id)}&customer_id=${encodeURIComponent(customerId)}&limit=4`,
        )
          .then((r) => setRelated((prev) => ({ ...prev, [a.article_id]: r.articles })))
          .catch(() => setRelated((prev) => ({ ...prev, [a.article_id]: [] })))
          .finally(() => setRelatedLoading(null));
      }
    }
  };

  return (
    <>
      <button
        onClick={() => setOpen(!open)}
        title="In-product help — context-aware article ranking deflects support tickets"
        style={{
          // Inside the midpane: offset from the viewport right by the
          // AitoPanel width (268px) plus a 24px gutter. The button sits
          // bottom-right of the main content area, not over the side panel.
          position: "fixed",
          bottom: 24,
          right: "calc(268px + 24px)",
          width: 44,
          height: 44,
          borderRadius: "50%",
          border: "none",
          background: open ? "var(--gold-dark)" : "var(--gold-mid)",
          color: open ? "#f5e8c0" : "#0d1520",
          fontSize: 22,
          fontWeight: 700,
          cursor: "pointer",
          boxShadow: "0 4px 12px rgba(0,0,0,0.2)",
          zIndex: 99,
          fontFamily: "inherit",
        }}
      >
        ?
      </button>

      {open && (
        <div
          style={{
            // Anchor right edge to the inner edge of the AitoPanel
            // (not the viewport) so the drawer slides over the
            // midpane and the AitoPanel stays visible.
            position: "fixed",
            top: 0,
            right: 268,
            bottom: 0,
            width: 420,
            maxWidth: "calc(100vw - 268px)",
            background: "var(--surface)",
            borderLeft: "1px solid var(--border)",
            boxShadow: "-4px 0 24px rgba(0,0,0,0.15)",
            zIndex: 100,
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--border2)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px" }}>
                In-product help · ticket deflection
              </div>
              <div style={{ fontSize: 13, color: "var(--text2)", marginTop: 2 }}>
                Context: <code style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, color: "var(--gold-dark)" }}>{pathname || "/"}</code>
              </div>
            </div>
            <button onClick={() => setOpen(false)} style={{ background: "transparent", border: "none", color: "var(--text3)", fontSize: 22, cursor: "pointer" }}>×</button>
          </div>

          {/* Deflection stats strip — concrete CPO-readable numbers */}
          <div style={{ padding: "10px 18px", borderBottom: "1px solid var(--border2)", background: "var(--surface2)", display: "flex", alignItems: "center", gap: 16 }}>
            <div style={{ display: "flex", flexDirection: "column" }}>
              <span style={{ fontSize: 15, fontWeight: 600, color: "var(--text)", fontFamily: "'IBM Plex Mono', monospace", lineHeight: 1 }}>
                {stats ? stats.impressions.toLocaleString() : "—"}
              </span>
              <span style={{ fontSize: 9.5, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".5px", marginTop: 3 }}>Impressions</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column" }}>
              <span style={{ fontSize: 15, fontWeight: 600, color: "var(--text)", fontFamily: "'IBM Plex Mono', monospace", lineHeight: 1 }}>
                {stats ? stats.clicks.toLocaleString() : "—"}
              </span>
              <span style={{ fontSize: 9.5, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".5px", marginTop: 3 }}>Clicks</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column" }}>
              <span style={{ fontSize: 15, fontWeight: 600, color: "var(--green)", fontFamily: "'IBM Plex Mono', monospace", lineHeight: 1 }}>
                {stats ? `${(stats.ctr * 100).toFixed(1)}%` : "—"}
              </span>
              <span style={{ fontSize: 9.5, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".5px", marginTop: 3 }}>CTR (deflection proxy)</span>
            </div>
          </div>

          <div style={{ padding: "12px 18px", borderBottom: "1px solid var(--border2)" }}>
            <input
              type="text"
              value={query}
              onChange={(e) => onQueryChange(e.target.value)}
              placeholder="Search help…"
              style={{
                width: "100%",
                padding: "8px 12px",
                fontSize: 13,
                border: "1px solid var(--border)",
                borderRadius: 6,
                background: "var(--surface2)",
                color: "var(--text)",
                outline: "none",
                fontFamily: "inherit",
              }}
            />
          </div>

          <div style={{ flex: 1, overflowY: "auto", padding: "8px 0" }}>
            {loading && articles.length === 0 && (
              // Show skeleton rows instead of plain "Loading…" text:
              // less obtrusive than a centered spinner on first open
              // when the prefetch hasn't completed yet (~600 ms).
              <div>
                {[0, 1, 2, 3, 4].map((i) => (
                  <div key={i} style={{ padding: "10px 18px", borderBottom: "1px solid var(--border2)" }}>
                    <div style={{ display: "flex", gap: 8, marginBottom: 6 }}>
                      <div className="skeleton" style={{ width: 56, height: 12, borderRadius: 3 }} />
                      <div className="skeleton" style={{ width: 70, height: 11, borderRadius: 3 }} />
                    </div>
                    <div className="skeleton" style={{ width: `${70 - (i * 8)}%`, height: 14, borderRadius: 3 }} />
                  </div>
                ))}
              </div>
            )}
            {!loading && articles.length === 0 && (
              <div style={{ padding: "24px 18px", color: "var(--text3)", fontSize: 12, textAlign: "center", lineHeight: 1.6 }}>
                No matching articles. Try a broader search term, or
                check the integrations / quality views.
              </div>
            )}
            {articles.map((a) => {
              const isExp = expanded === a.article_id;
              return (
                <div
                  key={a.article_id}
                  onClick={() => onArticleClick(a)}
                  style={{
                    padding: "10px 18px",
                    borderBottom: "1px solid var(--border2)",
                    cursor: "pointer",
                    background: isExp ? "var(--surface2)" : "transparent",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                    <span style={{
                      fontSize: 9,
                      fontWeight: 700,
                      textTransform: "uppercase",
                      letterSpacing: ".6px",
                      color: CATEGORY_COLOR[a.category] || "var(--text3)",
                      padding: "2px 6px",
                      border: `1px solid ${CATEGORY_COLOR[a.category] || "var(--border)"}`,
                      borderRadius: 3,
                    }}>
                      {CATEGORY_LABEL[a.category] || a.category}
                    </span>
                    {a.customer_id !== "*" && (
                      <span style={{ fontSize: 10, color: "var(--text3)", fontFamily: "'IBM Plex Mono', monospace" }}>{a.customer_id}</span>
                    )}
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)", lineHeight: 1.4 }}>
                    {a.title}
                  </div>
                  {isExp && (
                    <div style={{ marginTop: 8, fontSize: 12, color: "var(--text2)", lineHeight: 1.6 }}>
                      {a.body}
                      {a.tags && (
                        <div style={{ marginTop: 8, fontSize: 10, color: "var(--text3)" }}>
                          Tags: <span style={{ fontFamily: "'IBM Plex Mono', monospace" }}>{a.tags}</span>
                        </div>
                      )}

                      {/* Related articles via _recommend WHERE prev_article_id */}
                      <div style={{ marginTop: 14, paddingTop: 10, borderTop: "1px solid var(--border2)" }}>
                        <div style={{ fontSize: 10, fontWeight: 600, color: "var(--text3)", textTransform: "uppercase", letterSpacing: ".6px", marginBottom: 6 }}>
                          Users who read this also read
                        </div>
                        {relatedLoading === a.article_id && (
                          <div style={{ fontSize: 11, color: "var(--text3)", padding: "4px 0" }}>Loading…</div>
                        )}
                        {relatedLoading !== a.article_id && (related[a.article_id] ?? []).length === 0 && (
                          <div style={{ fontSize: 11, color: "var(--text3)", padding: "4px 0" }}>No related articles yet — clicks from this one are sparse.</div>
                        )}
                        {(related[a.article_id] ?? []).map((r) => (
                          <div
                            key={r.article_id}
                            onClick={(e) => { e.stopPropagation(); onArticleClick(r); }}
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: 8,
                              padding: "5px 0",
                              cursor: "pointer",
                            }}
                          >
                            <span style={{
                              fontSize: 9,
                              fontWeight: 700,
                              padding: "1px 5px",
                              border: `1px solid ${CATEGORY_COLOR[r.category] || "var(--border)"}`,
                              color: CATEGORY_COLOR[r.category] || "var(--text3)",
                              borderRadius: 3,
                              flexShrink: 0,
                            }}>
                              {(CATEGORY_LABEL[r.category] || r.category).split(" ")[0]}
                            </span>
                            <span style={{ fontSize: 12, color: "var(--text2)", lineHeight: 1.4 }}>
                              {r.title}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div style={{ padding: "10px 18px", borderTop: "1px solid var(--border2)", fontSize: 10, color: "var(--text3)", lineHeight: 1.5 }}>
            Context-aware help routes users to the right article instead of
            the support queue. Same{" "}
            <code style={{ fontFamily: "'IBM Plex Mono', monospace" }}>_recommend</code>
            {" "}substrate that fills GL codes — one impression table, no
            separate help-search service. Each shown article is an
            impression; each click trains the next ranking.
          </div>
        </div>
      )}
    </>
  );
}
