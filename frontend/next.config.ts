import type { NextConfig } from "next";
const config: NextConfig = {
  output: "standalone",
  distDir: process.env.NEXT_DIST_DIR || ".next",
};
export default config;
