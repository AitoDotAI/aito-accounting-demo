"use client";

import Link from "next/link";

type StepKey = "discover" | "review" | "measure";

interface Step {
  key: StepKey;
  label: string;
  href: string;
  caption: string;
  call: string;
}

const STEPS: Step[] = [
  {
    key: "discover",
    label: "1 · Discover",
    href: "/rulemining",
    caption: "Mine high-lift patterns from human overrides",
    call: "_relate",
  },
  {
    key: "review",
    label: "2 · Review",
    href: "/quality/overrides",
    caption: "Audit corrections, promote candidates",
    call: "_search overrides",
  },
  {
    key: "measure",
    label: "3 · Measure",
    href: "/quality/rules",
    caption: "Per-rule precision, coverage, trend",
    call: "_evaluate per rule",
  },
];

export default function GovernanceStepper({ active }: { active: StepKey }) {
  return (
    <div
      style={{
        background: "var(--surface)",
        borderBottom: "1px solid var(--border2)",
        padding: "10px 26px",
        display: "flex",
        alignItems: "center",
        gap: 6,
        flexWrap: "wrap",
        position: "relative",
        zIndex: 40,
      }}
    >
      <span
        style={{
          fontSize: 10,
          fontWeight: 600,
          color: "var(--text3)",
          textTransform: "uppercase",
          letterSpacing: ".6px",
          marginRight: 12,
          flexShrink: 0,
        }}
      >
        Governance loop
      </span>
      {STEPS.map((s, i) => {
        const isActive = s.key === active;
        return (
          <span key={s.key} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <Link
              href={s.href}
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 1,
                padding: "6px 12px",
                borderRadius: 6,
                border: isActive ? "1px solid var(--gold-dark)" : "1px solid var(--border)",
                background: isActive ? "var(--gold-light)" : "var(--surface)",
                color: isActive ? "var(--gold-dark)" : "var(--text2)",
                textDecoration: "none",
                fontFamily: "inherit",
                cursor: "pointer",
                minWidth: 0,
              }}
              title={s.caption}
            >
              <span style={{ fontSize: 12, fontWeight: isActive ? 600 : 500 }}>{s.label}</span>
              <span
                style={{
                  fontSize: 10,
                  color: isActive ? "var(--gold-dark)" : "var(--text3)",
                  fontFamily: "'IBM Plex Mono', monospace",
                  letterSpacing: ".2px",
                }}
              >
                {s.call}
              </span>
            </Link>
            {i < STEPS.length - 1 && (
              <span style={{ color: "var(--text3)", fontSize: 14, marginInline: 2 }}>→</span>
            )}
          </span>
        );
      })}
    </div>
  );
}
