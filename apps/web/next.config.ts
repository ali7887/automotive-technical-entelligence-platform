import type { NextConfig } from "next";

// Dev API target for the same-origin proxy below.
const devApiProxy = process.env.ATIP_DEV_API_PROXY ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Standalone output is opt-in (set by apps/web/Dockerfile) so `next dev`,
  // `next start`, and the CI build keep their default behavior.
  output: process.env.NEXT_OUTPUT_STANDALONE === "1" ? "standalone" : undefined,
  // No floating dev-tools badge over the product UI; system state lives in the
  // header status tray. Build/runtime errors still surface in the terminal.
  devIndicators: false,
  // The API is same-origin in every environment so the HttpOnly session
  // cookie is always first-party: production routes /api/* at the reverse
  // proxy (before requests ever reach this server), while dev proxies through
  // the Next server. SSE streams through this proxy unbuffered.
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${devApiProxy}/api/:path*` },
      { source: "/health/:path*", destination: `${devApiProxy}/health/:path*` },
    ];
  },
};

export default nextConfig;
