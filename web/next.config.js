// web/next.config.js
const path = require("path");

/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "images.unsplash.com",
      },
    ],
  },

  async redirects() {
    return [
      {
        source: "/watchlist",
        destination: "/dashboard",
        permanent: true,
      },
    ];
  },

  turbopack: {
    root: path.resolve(__dirname),
  },
  webpack: (config) => {
    // Silence optional peer dependency warnings for packages not installed
    config.resolve.fallback = {
      ...config.resolve.fallback,
      "@upstash/ratelimit": false,
      "@upstash/redis": false,
    };
    return config;
  },

  /**
   * Fallback security headers via Next.js headers config.
   * These apply even if middleware is bypassed (e.g., some CDN/edge deployments).
   * The middleware.ts sets these too — belt-and-suspenders.
   *
   * NOTE: CSP is intentionally NOT set here because it varies by dev/prod
   * and needs dynamic logic (nonces in future). middleware.ts handles CSP.
   */
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          {
            key: "X-Content-Type-Options",
            value: "nosniff",
          },
          {
            key: "X-Frame-Options",
            value: "DENY",
          },
          {
            key: "Referrer-Policy",
            value: "strict-origin-when-cross-origin",
          },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), payment=(), usb=(), bluetooth=()",
          },
        ],
      },
    ];
  },
};

module.exports = nextConfig;