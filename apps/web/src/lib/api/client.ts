import createClient from "openapi-fetch";

import type { paths } from "./schema";

// Same-origin by default: dev proxies /api/* through the Next server
// (next.config.ts rewrites), production routes it at the reverse proxy. An
// absolute NEXT_PUBLIC_API_URL is still honored, but it must be same-site or
// the HttpOnly session cookie will not flow.
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

export const api = createClient<paths>({ baseUrl: API_BASE_URL });

// A 401 anywhere outside the login screen means the session is gone
// (expired or revoked): return to login rather than surfacing raw errors.
api.use({
  onResponse({ response }) {
    if (
      response.status === 401 &&
      typeof window !== "undefined" &&
      window.location.pathname !== "/login"
    ) {
      window.location.assign("/login");
    }
  },
});
