import type { NextConfig } from "next";

/**
 * The portal and the API are served from one origin.
 *
 * Staff auth is a session cookie, so same-origin avoids third-party cookie
 * restrictions and CORS entirely. In development this rewrite stands in for
 * what nginx does in front of the deployed stack.
 */
const nextConfig: NextConfig = {
  // Served under /staff so one origin can carry the hub, the portal and the
  // API. Same-origin keeps the session cookie first-party, which is why the
  // portal is not simply pointed at the API subdomain.
  basePath: process.env.PORTAL_BASE_PATH || undefined,

  async rewrites() {
    const backend = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8000";
    return [{ source: "/v1/:path*", destination: `${backend}/v1/:path*` }];
  },
  // The portal handles no package tokens, but the dependency discipline from
  // docs/07 applies here too: nothing third-party gets to observe staff traffic.
  poweredByHeader: false,
};

export default nextConfig;
