import { errorMessage } from "./api/types";

/**
 * Pages reachable without a session. The api client must NOT bounce a 401 from
 * these to /login (they legitimately probe /api/auth/me while logged out), and
 * the header UserMenu must not render or query from them.
 */
export const AUTH_PAGES = ["/login", "/signup"] as const;

export function isAuthPage(pathname: string): boolean {
  return (AUTH_PAGES as readonly string[]).includes(pathname);
}

/**
 * A 401 outside the public auth pages means the session is gone (expired or
 * revoked) — return to /login rather than surfacing a raw error. On the auth
 * pages themselves a 401 is expected, so it must never trigger a redirect
 * (otherwise /signup bounces to /login the moment UserMenu probes the session).
 */
export function shouldRedirectToLogin(status: number, pathname: string): boolean {
  return status === 401 && !isAuthPage(pathname);
}

export interface SignOutDeps {
  /** Calls POST /api/auth/logout; resolves with the API client's error slot. */
  logout: () => Promise<{ error?: unknown }>;
  /** Drop cached auth/query state so nothing stale survives the redirect. */
  clearAuthState: () => void;
  redirect: (to: string) => void;
  onError: (message: string) => void;
}

/**
 * Revoke the session server-side, clear cached auth state, then return to
 * /login. On failure it surfaces a message and leaves the user signed in.
 * Never throws, so it is safe to call directly from an event handler without
 * leaving an unhandled promise rejection. Returns true on success.
 */
export async function performSignOut(deps: SignOutDeps): Promise<boolean> {
  try {
    const { error } = await deps.logout();
    if (error) {
      deps.onError(errorMessage(error, "Sign out failed. Please try again."));
      return false;
    }
  } catch {
    deps.onError("Sign out failed. Please check your connection and try again.");
    return false;
  }
  deps.clearAuthState();
  deps.redirect("/login");
  return true;
}
