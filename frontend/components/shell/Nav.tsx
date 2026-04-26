"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useCustomer } from "@/lib/customer-context";
import { apiFetch } from "@/lib/api";

interface NavItem {
  href: string;
  label: string;
  badgeKey?: "invoices" | "matching" | "anomalies";
  badgeRed?: boolean;
}

interface Badges {
  invoices: number;
  matching: number;
  anomalies: number;
}

const NAV_ITEMS: { section: string; items: NavItem[] }[] = [
  { section: "Payables", items: [
    { href: "/invoices", label: "Invoice Processing", badgeKey: "invoices" },
    { href: "/matching", label: "Payment Matching", badgeKey: "matching" },
    { href: "/formfill", label: "Smart Form Fill" },
  ]},
  { section: "Accounting", items: [
    { href: "/rulemining", label: "Rule Mining" },
    { href: "/anomalies", label: "Anomaly Detection", badgeKey: "anomalies", badgeRed: true },
  ]},
  { section: "Quality", items: [
    { href: "/quality/overview", label: "System Overview" },
    { href: "/quality/rules", label: "Rule Performance" },
    { href: "/quality/predictions", label: "Prediction Quality" },
    { href: "/quality/evaluations", label: "Evaluations Matrix" },
    { href: "/quality/overrides", label: "Human Overrides" },
  ]},
  { section: "Setup", items: [
    { href: "/integrations", label: "Integrations" },
  ]},
];

export default function Nav() {
  const pathname = usePathname();
  const { customerId } = useCustomer();
  const [badges, setBadges] = useState<Badges | null>(null);

  useEffect(() => {
    let active = true;
    setBadges(null);
    apiFetch<Badges>(`/api/nav/badges?customer_id=${encodeURIComponent(customerId)}`)
      .then((d) => { if (active) setBadges(d); })
      .catch(() => {});
    return () => { active = false; };
  }, [customerId]);

  return (
    <nav className="nav">
      <div className="nav-logo">
        <div className="nav-logo-mark">
          <div className="nav-logo-icon">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M3 4h10M3 7h10M3 10h6" stroke="#0d1520" strokeWidth="1.8" strokeLinecap="round"/>
            </svg>
          </div>
          <span className="nav-logo-text">Predictive Ledger</span>
        </div>
        <div className="nav-logo-sub">Powered by Aito.ai</div>
      </div>

      {NAV_ITEMS.map((section) => (
        <div key={section.section}>
          <div className="nav-section">{section.section}</div>
          {section.items.map((item) => {
            const count = item.badgeKey && badges ? badges[item.badgeKey] : undefined;
            const showBadge = count !== undefined && count > 0;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`nav-item ${pathname === item.href ? "active" : ""}`}
              >
                {item.label}
                {showBadge && (
                  <span className={`nav-badge ${item.badgeRed ? "red" : ""}`}>
                    {count}
                  </span>
                )}
              </Link>
            );
          })}
        </div>
      ))}

    </nav>
  );
}
