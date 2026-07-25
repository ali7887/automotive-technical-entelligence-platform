import { describe, expect, it, vi } from "vitest";

import { isAuthPage, performSignOut, shouldRedirectToLogin } from "./auth-nav";

describe("isAuthPage", () => {
  it("recognizes the public auth pages", () => {
    expect(isAuthPage("/login")).toBe(true);
    expect(isAuthPage("/signup")).toBe(true);
  });

  it("treats app pages as protected", () => {
    expect(isAuthPage("/")).toBe(false);
    expect(isAuthPage("/workspaces/abc")).toBe(false);
  });
});

describe("shouldRedirectToLogin", () => {
  it("redirects a 401 from a protected page", () => {
    expect(shouldRedirectToLogin(401, "/")).toBe(true);
    expect(shouldRedirectToLogin(401, "/workspaces/abc")).toBe(true);
  });

  it("never redirects from the auth pages themselves (the /signup bounce bug)", () => {
    expect(shouldRedirectToLogin(401, "/login")).toBe(false);
    expect(shouldRedirectToLogin(401, "/signup")).toBe(false);
  });

  it("ignores non-401 statuses", () => {
    expect(shouldRedirectToLogin(500, "/")).toBe(false);
    expect(shouldRedirectToLogin(200, "/")).toBe(false);
  });
});

describe("performSignOut", () => {
  function deps(overrides: Partial<Parameters<typeof performSignOut>[0]> = {}) {
    return {
      logout: vi.fn().mockResolvedValue({ error: undefined }),
      clearAuthState: vi.fn(),
      redirect: vi.fn(),
      onError: vi.fn(),
      ...overrides,
    };
  }

  it("clears state and redirects to /login on success", async () => {
    const d = deps();
    const ok = await performSignOut(d);
    expect(ok).toBe(true);
    expect(d.clearAuthState).toHaveBeenCalledOnce();
    expect(d.redirect).toHaveBeenCalledWith("/login");
    expect(d.onError).not.toHaveBeenCalled();
  });

  it("surfaces an API error and stays signed in", async () => {
    const d = deps({
      logout: vi.fn().mockResolvedValue({ error: { detail: "Server exploded" } }),
    });
    const ok = await performSignOut(d);
    expect(ok).toBe(false);
    expect(d.onError).toHaveBeenCalledWith("Server exploded");
    expect(d.clearAuthState).not.toHaveBeenCalled();
    expect(d.redirect).not.toHaveBeenCalled();
  });

  it("handles a network rejection without throwing", async () => {
    const d = deps({ logout: vi.fn().mockRejectedValue(new Error("network down")) });
    const ok = await performSignOut(d);
    expect(ok).toBe(false);
    expect(d.onError).toHaveBeenCalledOnce();
    expect(d.redirect).not.toHaveBeenCalled();
  });
});
