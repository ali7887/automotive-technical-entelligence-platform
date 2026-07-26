/**
 * Demo transport for the API-less deployment (NEXT_PUBLIC_DEMO_MODE=true).
 *
 * Injected as the custom `fetch` of the single openapi-fetch client
 * (see ../client.ts). It answers read `/api/*` requests from static fixtures so
 * the platform is fully browsable with no live backend, and returns a clean
 * read-only 403 for writes so the existing per-action error handling shows a
 * friendly toast instead of crashing. Anything that is not an ATIP API request
 * falls through to the real network `fetch`.
 *
 * This module is only reachable when the flag is on; with the flag off the
 * client uses the default fetch and none of this runs.
 */
import {
  DEMO_ASK,
  DEMO_DOCUMENTS,
  DEMO_EVIDENCE,
  DEMO_HEALTH,
  DEMO_USER,
  DEMO_WORKSPACES,
  demoSearchResponse,
} from "./fixtures";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** RFC 7807 problem+json, matching the API's error contract (see types.ts). */
function problem(status: number, code: string, title: string, detail: string): Response {
  return new Response(
    JSON.stringify({
      type: "about:blank",
      title,
      status,
      detail,
      instance: "",
      code,
      request_id: null,
    }),
    { status, headers: { "content-type": "application/problem+json" } },
  );
}

const READ_ONLY = () =>
  problem(
    403,
    "demo_read_only",
    "Read-only demo",
    "This is a read-only demo — changes are disabled. Deploy the ATIP API to enable writes.",
  );

const NOT_FOUND = () =>
  problem(404, "not_found", "Not found", "This resource is not available in the demo.");

// Path-parameter matchers. `[^/]+` captures a single UUID segment.
const RE = {
  workspaces: /^\/api\/workspaces\/?$/,
  workspace: /^\/api\/workspaces\/([^/]+)\/?$/,
  documents: /^\/api\/workspaces\/([^/]+)\/documents\/?$/,
  evidence: /^\/api\/workspaces\/([^/]+)\/evidence\/?$/,
  search: /^\/api\/workspaces\/([^/]+)\/search\/?$/,
  ask: /^\/api\/workspaces\/([^/]+)\/ask\/?$/,
  authMe: /^\/api\/auth\/me\/?$/,
  logout: /^\/api\/auth\/logout\/?$/,
  health: /^\/health\/?$/,
};

async function readQuery(request: Request): Promise<string> {
  try {
    const body = (await request.clone().json()) as { query?: unknown };
    return typeof body.query === "string" ? body.query : "";
  } catch {
    return "";
  }
}

/**
 * Resolve one request against the fixtures. Returns a Response for any ATIP API
 * path (read → data, write/unknown → read-only/not-found), or null to let the
 * caller fall through to the real network for non-API requests.
 */
async function route(request: Request): Promise<Response | null> {
  const url = new URL(request.url);
  const path = url.pathname;
  const method = request.method.toUpperCase();

  // Only the ATIP API surface is emulated; everything else is real.
  if (!path.startsWith("/api/") && !RE.health.test(path)) return null;

  if (RE.health.test(path)) return json(DEMO_HEALTH);

  if (RE.authMe.test(path)) return json(DEMO_USER);
  if (RE.logout.test(path)) return json({ ok: true });

  if (RE.workspaces.test(path) && method === "GET") return json(DEMO_WORKSPACES);

  let m = path.match(RE.documents);
  if (m && method === "GET") return json(DEMO_DOCUMENTS[m[1]] ?? []);

  m = path.match(RE.evidence);
  if (m && method === "GET") return json(DEMO_EVIDENCE[m[1]] ?? []);

  m = path.match(RE.search);
  if (m && method === "POST") return json(demoSearchResponse(m[1], await readQuery(request)));

  m = path.match(RE.ask);
  if (m && method === "POST") return json({ ...DEMO_ASK, workspace_id: m[1] });

  m = path.match(RE.workspace);
  if (m && method === "GET") {
    const ws = DEMO_WORKSPACES.find((w) => w.id === m![1]);
    return ws ? json(ws) : NOT_FOUND();
  }

  // Any other API request is a mutation (create/update/delete/upload/extract/
  // review) — disabled in the read-only demo.
  return READ_ONLY();
}

/** openapi-fetch custom fetch: fixtures for the API, real network otherwise. */
export const demoFetch: (input: Request) => Promise<Response> = async (input) => {
  const handled = await route(input);
  return handled ?? fetch(input);
};
