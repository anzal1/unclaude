import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Enable static export for bundling with Python package
  output: 'export',
  trailingSlash: true,
  
  // Disable image optimization (not compatible with static export)
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
