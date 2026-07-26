import createClient from "openapi-fetch";

import { shouldRedirectToLogin } from "../auth-nav";
import { demoFetch } from "./demo/transport";
import type { paths } from "./schema";

// Same-origin by default: dev proxies /api/* through the Next server
// (next.config.ts rewrites), production routes it at the reverse proxy. An
// absolute NEXT_PUBLIC_API_URL is still honored, but it must be same-site or
// the HttpOnly session cookie will not flow.
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

// Temporary demo mode. When on, the app may be deployed frontend-only (no live
// API): the transport below answers /api/* reads from static fixtures and makes
// writes a clean read-only error. A 401 must also not bounce to /login (there
// is none). Unset NEXT_PUBLIC_DEMO_MODE to restore the normal behavior; the
// demo transport is then never wired in. See demo/transport.ts and middleware.ts.
const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

export const api = createClient<paths>({
  baseUrl: API_BASE_URL,
  ...(DEMO_MODE ? { fetch: demoFetch } : {}),
});

// A 401 outside the public auth pages means the session is gone (expired or
// revoked): return to login rather than surfacing raw errors. /login and
// /signup are exempt — they legitimately 401 while probing the session.
api.use({
  onResponse({ response }) {
    if (
      !DEMO_MODE &&
      typeof window !== "undefined" &&
      shouldRedirectToLogin(response.status, window.location.pathname)
    ) {
      window.location.assign("/login");
    }
  },
});
