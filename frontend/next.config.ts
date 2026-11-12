import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // Keep the standalone server at the project root on workspace-aware builds.
  outputFileTracingRoot: process.cwd(),
};

export default nextConfig;
