import { NextResponse, type NextRequest } from "next/server";

// Must match the API's SESSION_COOKIE_NAME.
const SESSION_COOKIE = "atip_session";

// Reachable without a session: login and public self-service signup.
const PUBLIC_PATHS = new Set(["/login", "/signup"]);

// Temporary demo mode. When NEXT_PUBLIC_DEMO_MODE=true the platform is entered
// directly with no login/signup: auth pages redirect into the app and every
// page renders without a session. There is no live API in this mode — the
// browser client serves /api/* from static fixtures (lib/api/demo/transport.ts)
// — so no session needs to be established here. Set the flag to false or unset
// it to restore the normal auth flow untouched. See also user-menu.tsx (auth
// UI) and lib/api/client.ts (transport + 401 handling).
const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

/**
 * Page-level guard only: redirects users without a session cookie to /login
 * before any page renders. This is UX, not security — the API validates the
 * session server-side on every request and answers 401/403 regardless.
 */
export function middleware(request: NextRequest) {
  const hasSession = request.cookies.has(SESSION_COOKIE);
  const isPublic = PUBLIC_PATHS.has(request.nextUrl.pathname);

  // Demo mode: no login/signup. Auth pages go straight to the app; every other
  // page renders directly (the fixture transport backs the UI). Everything
  // below (the normal guard) is left exactly as-is.
  if (DEMO_MODE) {
    if (isPublic) {
      return NextResponse.redirect(new URL("/", request.url));
    }
    return NextResponse.next();
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
