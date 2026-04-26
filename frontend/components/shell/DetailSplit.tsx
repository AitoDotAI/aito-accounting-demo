"use client";

import { useEffect, useRef, useState, ReactNode } from "react";

interface DetailSplitProps {
  /** Top half (the master grid). */
  top: ReactNode;
  /** Bottom half — only rendered when `open` is true. */
  bottom: ReactNode;
  /** Whether the bottom panel is open. */
  open: boolean;
  /** Called when user clicks the close × in the bottom panel header. */
  onClose: () => void;
  /** Title shown at the top of the bottom panel. */
  title?: string;
  /** Initial height of the bottom panel in px. Persisted across sessions. */
  initialBottomHeight?: number;
  /** localStorage key for persisting splitter position. */
  storageKey?: string;
}

/**
 * Top/bottom split with a draggable resize handle. Mirrors the
 * master-detail UX of Procountor, Visma, NetSuite — click a row,
 * details open below; drag the splitter to give either half more
 * room. Splitter position persists in localStorage.
 *
 * The component takes the FULL height of its parent. Caller should
 * place it in a flex column or fixed-height container.
 */
export default function DetailSplit({
  top,
  bottom,
  open,
  onClose,
  title,
  initialBottomHeight = 360,
  storageKey = "detail-split-height",
}: DetailSplitProps) {
  const [bottomHeight, setBottomHeight] = useState(initialBottomHeight);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const draggingRef = useRef(false);

  // Restore stored height once on mount
  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = localStorage.getItem(storageKey);
    if (stored) {
      const n = parseInt(stored, 10);
      if (!isNaN(n) && n > 100 && n < 800) setBottomHeight(n);
    }
  }, [storageKey]);

  const onMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    draggingRef.current = true;
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";
  };

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!draggingRef.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      // Bottom height is from the mouse Y to the container bottom
      const newHeight = Math.max(120, Math.min(rect.height - 100, rect.bottom - e.clientY));
      setBottomHeight(newHeight);
    };
    const onUp = () => {
      if (!draggingRef.current) return;
      draggingRef.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      // Persist
      if (typeof window !== "undefined") {
        localStorage.setItem(storageKey, String(Math.round(bottomHeight)));
      }
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [bottomHeight, storageKey]);

  return (
    <div ref={containerRef} style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>{top}</div>

      {open && (
        <>
          <div
            onMouseDown={onMouseDown}
            title="Drag to resize"
            style={{
              height: 6,
              cursor: "row-resize",
              background: "var(--border2)",
              borderTop: "1px solid var(--border)",
              borderBottom: "1px solid var(--border)",
              flexShrink: 0,
              position: "relative",
            }}
          >
            <div style={{
              position: "absolute",
              top: 1,
              left: "50%",
              transform: "translateX(-50%)",
              width: 36,
              height: 2,
              background: "var(--text3)",
              borderRadius: 1,
              opacity: 0.4,
            }} />
          </div>

          <div style={{
            height: bottomHeight,
            flexShrink: 0,
            display: "flex",
            flexDirection: "column",
            background: "var(--surface)",
            borderTop: "1px solid var(--border2)",
            minHeight: 120,
          }}>
            <div style={{
              padding: "10px 16px",
              borderBottom: "1px solid var(--border2)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              background: "var(--surface2)",
              flexShrink: 0,
            }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>{title}</div>
              <button
                onClick={onClose}
                title="Close detail panel"
                style={{
                  background: "transparent",
                  border: "none",
                  color: "var(--text3)",
                  fontSize: 18,
                  cursor: "pointer",
                  padding: "0 4px",
                  lineHeight: 1,
                }}
              >
                ×
              </button>
            </div>
            <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>{bottom}</div>
          </div>
        </>
      )}
    </div>
  );
}
