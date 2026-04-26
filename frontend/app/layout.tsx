"use client";

import "./globals.css";
import { CustomerProvider } from "@/lib/customer-context";
import { TourProvider } from "@/lib/tour-context";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <CustomerProvider>
          <TourProvider>
            <div className="app">
              {children}
            </div>
          </TourProvider>
        </CustomerProvider>
      </body>
    </html>
  );
}
