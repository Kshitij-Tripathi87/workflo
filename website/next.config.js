/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  async redirects() {
    return [
      {
        source: "/docs",
        destination: "https://github.com/Kshitij-Tripathi87/workflo",
        permanent: false,
      },
    ];
  },
};

module.exports = nextConfig;
