import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output is opt-in (set by apps/web/Dockerfile) so `next dev`,
  // `next start`, and the CI build keep their default behavior.
  output: process.env.NEXT_OUTPUT_STANDALONE === "1" ? "standalone" : undefined,
};

export default nextConfig;
