/** @type {import('next').NextConfig} */
const engineOrigin = process.env.REALM_ENGINE_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/engine/:path*",
        destination: `${engineOrigin.replace(/\/$/, "")}/:path*`,
      },
    ];
  },
};

export default nextConfig;
