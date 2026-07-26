import { NextResponse, type NextRequest } from "next/server";

// Must match the API's SESSION_COOKIE_NAME.
const SESSION_COOKIE = "atip_session";

// Reachable without a session: login and public self-service signup.
const PUBLIC_PATHS = new Set(["/login", "/signup"]);

// Temporary demo mode. When NEXT_PUBLIC_DEMO_MODE=true the platform is entered
// directly with no login/signup: auth pages redirect into the app, and this
// gate transparently establishes a real session for a seeded demo account.
// (The API still enforces sessions server-side, so a genuine session — not just
// a skipped redirect — is required for the app to work.) Set the flag to false
// or unset it to restore the normal auth flow untouched. The demo credentials
// are server-only (never NEXT_PUBLIC_), so they are not exposed to the browser.
// See also user-menu.tsx (auth UI) and lib/api/client.ts (401 handling).
const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";
const DEMO_EMAIL = process.env.DEMO_LOGIN_EMAIL ?? "";
const DEMO_PASSWORD = process.env.DEMO_LOGIN_PASSWORD ?? "";

/**
 * Best-effort demo sign-in: logs the demo account in through the same-origin
 * API and forwards its Set-Cookie onto the page response, so the very first
 * (cookieless) load is already authenticated. Failures are swallowed — the page
 * still renders rather than looping — so a misconfigured demo degrades quietly.
 */
async function attachDemoSession(request: NextRequest, response: NextResponse) {
  if (!DEMO_EMAIL || !DEMO_PASSWORD) return;
  try {
    const login = await fetch(new URL("/api/auth/login", request.nextUrl.origin), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email: DEMO_EMAIL, password: DEMO_PASSWORD }),
    });
    if (!login.ok) return;
    for (const cookie of login.headers.getSetCookie()) {
      response.headers.append("set-cookie", cookie);
    }
  } catch {
    // API unreachable: leave the page unauthenticated rather than break it.
  }
}

/**
 * Page-level guard only: redirects users without a session cookie to /login
 * before any page renders. This is UX, not security — the API validates the
 * session server-side on every request and answers 401/403 regardless.
 */
export async function middleware(request: NextRequest) {
  const hasSession = request.cookies.has(SESSION_COOKIE);
  const isPublic = PUBLIC_PATHS.has(request.nextUrl.pathname);

  // Demo mode: no login/signup. Auth pages go straight to the app, and a demo
  // session is minted on the first cookieless load so the platform opens
  // directly. Everything below (the normal guard) is left exactly as-is.
  if (DEMO_MODE) {
    if (isPublic) {
      return NextResponse.redirect(new URL("/", request.url));
    }
    const response = NextResponse.next();
    if (!hasSession) {
      await attachDemoSession(request, response);
    }
    return response;
  }

  if (!hasSession && !isPublic) {
    const login = new URL("/login", request.url);
    if (request.nextUrl.pathname !== "/") {
      login.searchParams.set("next", request.nextUrl.pathname);
    }
    return NextResponse.redirect(login);
  }
  // Already authenticated: keep users off the login/signup pages.
  if (hasSession && isPublic) {
    return NextResponse.redirect(new URL("/", request.url));
  }
  return NextResponse.next();
}

export const config = {
  // pages only: the API proxy, health probes, and static assets pass through
  matcher: ["/((?!api|health|_next/static|_next/image|favicon.ico).*)"],
};
