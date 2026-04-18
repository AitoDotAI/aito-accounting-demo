import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV === "development";

const nextConfig: NextConfig = {
  // Static export for production — FastAPI serves the built files
  ...(isDev ? {} : { output: "export" }),

  // Generate /invoices/index.html instead of /invoices.html
  // so FastAPI StaticFiles(html=True) can serve them
  trailingSlash: true,

  // In dev mode, proxy API calls to the FastAPI backend
  ...(isDev
    ? {
        async rewrites() {
          return [
            {
              source: "/api/:path*",
              destination: "http://localhost:8200/api/:path*",
            },
          ];
        },
      }
    : {}),
};

export default nextConfig;
