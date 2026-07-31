/** @type {import('next').NextConfig} */
const securityHeaders = [
  { key: "X-DNS-Prefetch-Control", value: "on" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  {
    key: "Content-Security-Policy",
    // 'unsafe-inline' is required by Next.js production builds via the
    // runtime script hashes it generates. 'unsafe-eval' is intentionally
    // omitted - eval()/new Function() are not used anywhere in the app.
    value:
      "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' http://localhost:8000 http://127.0.0.1:8000; font-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self';",
  },
];

// Server-side rewrites use a private (non-NEXT_PUBLIC_) env var so backend
// URLs don't leak into the client bundle. The public var is consumed only
// where the client genuinely needs it (lib/api.ts).
const SERVER_API_BASE = process.env.API_BASE_URL || "http://localhost:8000";

const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: securityHeaders,
      },
    ];
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${SERVER_API_BASE}/api/:path*` },
    ];
  },
};

module.exports = nextConfig;
