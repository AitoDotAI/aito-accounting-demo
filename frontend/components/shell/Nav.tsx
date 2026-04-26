"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

interface NavItem {
  href: string;
  label: string;
  badge?: string;
  badgeRed?: boolean;
}

const NAV_ITEMS: { section: string; items: NavItem[] }[] = [
  { section: "Payables", items: [
    { href: "/invoices", label: "Invoice Processing", badge: "12" },
    { href: "/matching", label: "Payment Matching", badge: "5" },
    { href: "/formfill", label: "Smart Form Fill" },
  ]},
  { section: "Accounting", items: [
    { href: "/rulemining", label: "Rule Mining" },
    { href: "/anomalies", label: "Anomaly Detection", badge: "3", badgeRed: true },
  ]},
  { section: "Quality", items: [
    { href: "/quality/overview", label: "System Overview" },
    { href: "/quality/rules", label: "Rule Performance" },
    { href: "/quality/predictions", label: "Prediction Quality" },
    { href: "/quality/overrides", label: "Human Overrides" },
  ]},
  { section: "Setup", items: [
    { href: "/integrations", label: "Integrations" },
  ]},
];

export default function Nav() {
  const pathname = usePathname();

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
          {section.items.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`nav-item ${pathname === item.href ? "active" : ""}`}
            >
              {item.label}
              {item.badge && (
                <span className={`nav-badge ${item.badgeRed ? "red" : ""}`}>
                  {item.badge}
                </span>
              )}
            </Link>
          ))}
        </div>
      ))}

      <div className="nav-user">
        <div className="nav-item">Tiina M&#228;kinen</div>
      </div>
    </nav>
  );
}
