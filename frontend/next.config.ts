import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Docker deploy sets NEXT_OUTPUT=standalone to get a self-contained server.js.
  ...(process.env.NEXT_OUTPUT === "standalone" ? { output: "standalone" as const } : {}),
  cacheComponents: true,
  partialPrefetching: true,
  async headers() {
    return [
      {
        // /finn-demo.html?download=1 saves the offline demo instead of opening it.
        source: "/finn-demo.html",
        has: [{ type: "query", key: "download" }],
        headers: [{ key: "Content-Disposition", value: 'attachment; filename="finn-demo.html"' }],
      },
    ];
  },
  async rewrites() {
    const backendOrigin = process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000";
    return [
      {
        source: "/api/v1/:path*",
        destination: `${backendOrigin}/api/v1/:path*`,
      },
    ];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
