import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Every page reads per-user data from Supabase, so the app renders dynamically.
  cacheComponents: false,
  turbopack: {
    root: process.cwd(),
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
