"use client";
import Nav from "@/components/shell/Nav";
import TopBar from "@/components/shell/TopBar";

export default function Page() {
  const title = {
    formfill: "Smart Form Fill",
    matching: "Payment Matching", 
    rulemining: "Rule Mining",
    anomalies: "Anomaly Detection",
  } as Record<string, string>;
  const name = "$route";
  return (
    <>
      <Nav />
      <div className="main">
        <TopBar breadcrumb="—" title={title[name] || name} subtitle="Coming soon" />
        <div className="content">
          <div style={{ textAlign: "center", color: "var(--text3)", padding: 48 }}>
            This view will be ported in the next phase.
          </div>
        </div>
      </div>
    </>
  );
}
