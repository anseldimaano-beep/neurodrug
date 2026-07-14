/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  async rewrites() {
    // Proxy all /api/* calls to the backend container so the browser never
    // makes a cross-origin request — eliminates CORS entirely.
    // Uses the Docker service name 'api' inside the container network.
    const apiUrl = process.env.INTERNAL_API_URL || 'http://api:8000';
    return [
      {
        source: '/api/:path*',
        destination: `${apiUrl}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
