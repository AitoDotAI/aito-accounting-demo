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
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastImpressionPage = useRef<string>("");

  // Fetch contextual articles on open or page/customer change
  useEffect(() => {
    if (!open) return;
    setLoading(true);
    const url = `/api/help/search?customer_id=${encodeURIComponent(customerId)}&page=${encodeURIComponent(pathname || "")}&q=${encodeURIComponent(query)}&limit=5`;
    apiFetch<{ articles: Article[] }>(url)
      .then((d) => {
        setArticles(d.articles ?? []);
        // Log impressions for every article shown — but only once per
        // (page, customer, query) to avoid spam.
        const key = `${pathname}|${customerId}|${query}`;
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
                query,
                clicked: false,
              }),
            }).catch(() => {});
          }
        }
      })
      .catch(() => setArticles([]))
      .finally(() => setLoading(false));
  }, [open, pathname, customerId, query]);

  const onQueryChange = (v: string) => {
    setQuery(v);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      // Re-fetch happens via useEffect on `query`
    }, 250);
  };

  const onArticleClick = (a: Article) => {
    setExpanded(expanded === a.article_id ? null : a.article_id);
    // Log click for CTR ranking
    apiFetch("/api/help/impression", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        article_id: a.article_id,
        customer_id: customerId,
        page: pathname || "",
        query,
        clicked: true,
      }),
    }).catch(() => {});
  };

  return (
    <>
      <button
        onClick={() => setOpen(!open)}
        title="Help (?) "
        style={{
          position: "fixed",
          bottom: 24,
          right: 24,
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
            position: "fixed",
            top: 0,
            right: 0,
            bottom: 0,
            width: 420,
            maxWidth: "100vw",
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
                Help · ranked by Aito
              </div>
              <div style={{ fontSize: 13, color: "var(--text2)", marginTop: 2 }}>
                Context: <code style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, color: "var(--gold-dark)" }}>{pathname || "/"}</code>
              </div>
            </div>
            <button onClick={() => setOpen(false)} style={{ background: "transparent", border: "none", color: "var(--text3)", fontSize: 22, cursor: "pointer" }}>×</button>
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
            {loading && (
              <div style={{ padding: "24px 18px", color: "var(--text3)", fontSize: 12, textAlign: "center" }}>
                Loading…
              </div>
            )}
            {!loading && articles.length === 0 && (
              <div style={{ padding: "24px 18px", color: "var(--text3)", fontSize: 12, textAlign: "center", lineHeight: 1.6 }}>
                No matching articles. Try a broader search term, or
                check the integrations / quality views.
              </div>
            )}
            {!loading && articles.map((a) => {
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
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div style={{ padding: "10px 18px", borderTop: "1px solid var(--border2)", fontSize: 10, color: "var(--text3)", lineHeight: 1.5 }}>
            Articles ranked by historical click-through-rate via Aito{" "}
            <code style={{ fontFamily: "'IBM Plex Mono', monospace" }}>_predict article_id</code>.{" "}
            Each shown article is an impression; each click trains the next ranking.
          </div>
        </div>
      )}
    </>
  );
}
