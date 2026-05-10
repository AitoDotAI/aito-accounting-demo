"use client";

import Script from "next/script";
import "./globals.css";
import { CustomerProvider } from "@/lib/customer-context";
import { TourProvider } from "@/lib/tour-context";
import { GuidedTourProvider } from "@/lib/guided-tour";
import HeadlineBanner from "@/components/shell/HeadlineBanner";
import HelpDrawer from "@/components/help/HelpDrawer";
import GuidedTourOverlay from "@/components/shell/GuidedTourOverlay";
import LatencyTicker from "@/components/shell/LatencyTicker";
import Analytics from "@/components/shell/Analytics";

// Google Analytics 4 measurement ID. Same property aito-demo uses
// (`public/index.html`) so the accounting demo lands in the same
// GA4 view. anonymize_ip + cookie_expires:0 mirror that file too.
const GA_MEASUREMENT_ID = "G-FDTBRCMZWJ";

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
              <Analytics />
            </GuidedTourProvider>
          </TourProvider>
        </CustomerProvider>

        <Script
          src={`https://www.googletagmanager.com/gtag/js?id=${GA_MEASUREMENT_ID}`}
          strategy="afterInteractive"
        />
        <Script id="ga-init" strategy="afterInteractive">
          {`
            window.dataLayer = window.dataLayer || [];
            function gtag(){dataLayer.push(arguments);}
            gtag('js', new Date());
            gtag('config', '${GA_MEASUREMENT_ID}', {
              anonymize_ip: true,
              cookie_expires: 0,
            });
          `}
        </Script>
      </body>
    </html>
  );
}
