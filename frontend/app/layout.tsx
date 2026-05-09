"use client";

import "./globals.css";
import { CustomerProvider } from "@/lib/customer-context";
import { TourProvider } from "@/lib/tour-context";
import { GuidedTourProvider } from "@/lib/guided-tour";
import HeadlineBanner from "@/components/shell/HeadlineBanner";
import HelpDrawer from "@/components/help/HelpDrawer";
import GuidedTourOverlay from "@/components/shell/GuidedTourOverlay";
import LatencyTicker from "@/components/shell/LatencyTicker";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <CustomerProvider>
          <TourProvider>
            <GuidedTourProvider>
              <HeadlineBanner />
              <div className="app">
                {children}
              </div>
              <HelpDrawer />
              <GuidedTourOverlay />
              <LatencyTicker />
            </GuidedTourProvider>
          </TourProvider>
        </CustomerProvider>
      </body>
    </html>
  );
}
