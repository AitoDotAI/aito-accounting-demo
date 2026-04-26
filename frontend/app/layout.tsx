"use client";

import "./globals.css";
import { CustomerProvider } from "@/lib/customer-context";
import { TourProvider } from "@/lib/tour-context";
import HeadlineBanner from "@/components/shell/HeadlineBanner";
import HelpDrawer from "@/components/help/HelpDrawer";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <CustomerProvider>
          <TourProvider>
            <HeadlineBanner />
            <div className="app">
              {children}
            </div>
            <HelpDrawer />
          </TourProvider>
        </CustomerProvider>
      </body>
    </html>
  );
}
