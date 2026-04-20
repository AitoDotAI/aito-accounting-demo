import "./globals.css";

export const metadata = {
  title: "Predictive Ledger — Aito Demo",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="app">
          {children}
        </div>
      </body>
    </html>
  );
}
