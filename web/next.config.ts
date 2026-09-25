import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output produces a lean, self-contained server bundle for the Docker runtime
  // image (see web/Dockerfile).
  output: "standalone",
  reactStrictMode: true,
};

export default nextConfig;
