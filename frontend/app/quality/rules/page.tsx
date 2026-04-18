"use client";
import Nav from "@/components/shell/Nav";
import TopBar from "@/components/shell/TopBar";

export default function Page() {
  return (
    <>
      <Nav />
      <div className="main">
        <TopBar breadcrumb="Quality" title="$route" subtitle="Coming soon" />
        <div className="content">
          <div style={{ textAlign: "center", color: "var(--text3)", padding: 48 }}>
            This view will be ported in the next phase.
          </div>
        </div>
      </div>
    </>
  );
}
