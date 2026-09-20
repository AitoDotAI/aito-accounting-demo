"use client";

import { useEffect, useState } from "react";
import { onAitoLatency, type AitoLatencySample } from "@/lib/api";

interface OpEntry {
  id: number;
  op: string;
  ms: number;
  at: number;
}

const VISIBLE = 4;        // how many recent entries to keep on screen
const FADE_AFTER_MS = 6000; // entries older than this fade out

function fmtMs(ms: number): string {
  if (Number.isNaN(ms)) return "?";
  if (ms < 10) return ms.toFixed(1) + "ms";
  if (ms < 1000) return Math.round(ms) + "ms";
  return (ms / 1000).toFixed(2) + "s";
}

function color(op: string): string {
  // Hue per op makes the tape readable at a glance. Cluster colors
  // so the same op is consistent across renders.
  if (op.startsWith("_predict")) return "#6ab87a";
  if (op.startsWith("_relate")) return "#9870d8";
  if (op.startsWith("_recommend")) return "#5a9ad8";
  if (op.startsWith("_search")) return "#d4a030";
  if (op.startsWith("_evaluate")) return "#d06060";
  if (op.startsWith("_match")) return "#12B5AD";
  if (op.startsWith("data:")) return "#8a8060"; // file uploads, schema
  return "#a89848";
}

/**
 * Live tape of recent Aito calls, fixed-position in the bottom-left
 * corner. One pill per call:
 *
 *     _predict 28ms   _relate 142ms   _search 11ms
 *
 * Persistent CTO-readable proof of the latency claims as queries
 * fly. Color-coded per op so the same operation is recognisable
 * across pages.
 *
 * Hidden until the first call arrives so the corner stays clean
 * on routes that don't touch Aito.
 */
export default function LatencyTicker() {
  const [entries, setEntries] = useState<OpEntry[]>([]);
  const [, setTick] = useState(0); // re-render to fade out

  useEffect(() => {
    let nextId = 1;
    const unsubscribe = onAitoLatency((sample: AitoLatencySample) => {
      const now = Date.now();
      const newOnes: OpEntry[] = (sample.ops.length > 0
        ? sample.ops
        : [{ op: "request", ms: sample.ms }]
      ).map((o) => ({ id: nextId++, op: o.op, ms: o.ms, at: now }));
      setEntries((prev) => [...prev, ...newOnes].slice(-VISIBLE));
    });
    // Tick once a second so faded-out entries actually disappear
    // even when no new calls are coming in.
    const interval = setInterval(() => setTick((n) => n + 1), 1000);
    return () => {
      unsubscribe();
      clearInterval(interval);
    };
  }, []);

  // Drop entries that are fully faded so the corner stays empty.
  const now = Date.now();
  const visible = entries.filter((e) => now - e.at < FADE_AFTER_MS + 1000);

  if (visible.length === 0) return null;

  return (
    <div
      className="latency-ticker"
      aria-hidden="true"
      style={{
        position: "fixed",
        left: 16,
        bottom: 16,
        display: "flex",
        flexDirection: "row",
        gap: 6,
        zIndex: 90,
        pointerEvents: "none",
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: 11,
      }}
    >
      {visible.map((e) => {
        const age = now - e.at;
        const opacity = age > FADE_AFTER_MS ? 0 : 1 - Math.max(0, age - 4000) / 2000;
        return (
          <span
            key={e.id}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 5,
              padding: "3px 8px",
              borderRadius: 12,
              background: "var(--surface)",
              border: `1px solid ${color(e.op)}66`,
              color: "var(--text)",
              opacity,
              transition: "opacity 1s ease",
              boxShadow: "0 1px 3px rgba(0,0,0,.06)",
              whiteSpace: "nowrap",
            }}
          >
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: color(e.op) }} />
            <span style={{ color: "var(--text3)" }}>{e.op}</span>
            <span style={{ fontWeight: 600 }}>{fmtMs(e.ms)}</span>
          </span>
        );
      })}
    </div>
  );
}
