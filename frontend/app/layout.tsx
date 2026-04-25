"use client";

import "./globals.css";
import { CustomerProvider } from "@/lib/customer-context";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <CustomerProvider>
          <div className="app">
            {children}
          </div>
        </CustomerProvider>
      </body>
    </html>
  );
}
