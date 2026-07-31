/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  async redirects() {
    return [
      { source: "/docs", destination: "https://docs.cortex.dev", permanent: true },
    ];
  },
};

module.exports = nextConfig;
