import { NextResponse, type NextRequest } from "next/server";

// Must match the API's SESSION_COOKIE_NAME.
const SESSION_COOKIE = "atip_session";

/**
 * Page-level guard only: redirects users without a session cookie to /login
 * before any page renders. This is UX, not security — the API validates the
 * session server-side on every request and answers 401/403 regardless.
 */
export function middleware(request: NextRequest) {
  const hasSession = request.cookies.has(SESSION_COOKIE);
  const isLogin = request.nextUrl.pathname === "/login";

  if (!hasSession && !isLogin) {
    const login = new URL("/login", request.url);
    if (request.nextUrl.pathname !== "/") {
      login.searchParams.set("next", request.nextUrl.pathname);
    }
    return NextResponse.redirect(login);
  }
  if (hasSession && isLogin) {
    return NextResponse.redirect(new URL("/", request.url));
  }
  return NextResponse.next();
}

export const config = {
  // pages only: the API proxy, health probes, and static assets pass through
  matcher: ["/((?!api|health|_next/static|_next/image|favicon.ico).*)"],
};
