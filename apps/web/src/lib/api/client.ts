import createClient from "openapi-fetch";

import { demoFetch } from "./demo/transport";
import type { paths } from "./schema";

// Same-origin by default: dev proxies /api/* through the Next server
// (next.config.ts rewrites), production routes it at the reverse proxy. An
// absolute NEXT_PUBLIC_API_URL is still honored, but it must be same-site.
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

// Optional API-less demo mode (NEXT_PUBLIC_DEMO_MODE=true): the transport below
// answers /api/* from static fixtures. Off by default; left inert otherwise.
const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

// Authentication has been removed: the API runs open (every request resolves to
// a default admin), so there is no session to expire and no /login to bounce a
// 401 to. Errors surface where they occur.
export const api = createClient<paths>({
  baseUrl: API_BASE_URL,
  ...(DEMO_MODE ? { fetch: demoFetch } : {}),
});
