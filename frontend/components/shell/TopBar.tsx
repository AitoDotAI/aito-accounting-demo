"use client";

import CustomerSelector from "./CustomerSelector";
import ColdStartBanner from "./ColdStartBanner";
import LatencyBadge from "./LatencyBadge";
import StartTourButton from "./StartTourButton";
import { useTour } from "@/lib/tour-context";

interface TopBarProps {
  breadcrumb: string;
  title: string;
  /** Plain string or React node — pages use the node form to inline a spinner. */
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  live?: boolean;
}

export default function TopBar({ breadcrumb, title, subtitle, actions, live }: TopBarProps) {
  const { tourOn, setTourOn } = useTour();
  return (
    <>
    <div className="topbar">
      <div>
        <div className="topbar-breadcrumb">{breadcrumb}</div>
        <div className="topbar-title">{title}</div>
      </div>
      {subtitle && (
        <>
          <div className="topbar-sep" />
          <div className="topbar-sub">{subtitle}</div>
        </>
      )}
      <div className="topbar-right">
        <StartTourButton />
        <CustomerSelector />
        <button
          onClick={() => setTourOn(!tourOn)}
          title="Highlight which UI elements came from which Aito call"
          style={{
            padding: "5px 10px",
            borderRadius: 6,
            border: "1px solid " + (tourOn ? "var(--gold-dark)" : "var(--border)"),
            fontSize: 11,
            fontFamily: "inherit",
            background: tourOn ? "var(--gold-light)" : "var(--surface)",
            color: tourOn ? "var(--gold-dark)" : "var(--text2)",
            cursor: "pointer",
            fontWeight: tourOn ? 600 : 500,
          }}
        >
          {tourOn ? "Data flow ON" : "Data flow"}
        </button>
        <LatencyBadge />
        {live && <span className="live-dot">Live</span>}
        {actions}
      </div>
    </div>
    <ColdStartBanner />
    </>
  );
}
