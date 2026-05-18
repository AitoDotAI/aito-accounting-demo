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

// GA4 measurement ID is provisioned at build time via
// aito-demo-server's env_secrets (Azure Key Vault). Same GA4 property
// as the other Aito demos so events land in the same view.
const GA_MEASUREMENT_ID = process.env.NEXT_PUBLIC_GA4_MEASUREMENT_ID;

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

        {GA_MEASUREMENT_ID && (
          <>
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
          </>
        )}
      </body>
    </html>
  );
}
