"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, LogOut, Moon, Sun } from "lucide-react";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";
import type { User } from "@/lib/api/types";
import { isAuthPage, performSignOut } from "@/lib/auth-nav";

// Temporary demo mode: the platform runs login-less, so the header shows no
// identity or sign-out — only the theme toggle. Unset NEXT_PUBLIC_DEMO_MODE to
// restore the normal user menu. See middleware.ts for the full demo-mode note.
const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

/** Current user + sign-out, shown in the header on authenticated pages. */
export function UserMenu() {
  const pathname = usePathname();
  // Never query or render on the public auth pages: /api/auth/me 401s there,
  // which would otherwise trip the client's redirect-to-login. In demo mode
  // there is no session identity to show, so the probe is skipped entirely.
  const onAuthPage = isAuthPage(pathname);
  const queryClient = useQueryClient();
  const [signingOut, setSigningOut] = useState(false);

  const { data: user } = useQuery<User>({
    queryKey: ["auth", "me"],
    enabled: !onAuthPage && !DEMO_MODE,
    retry: false,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/auth/me");
      if (!data) throw new Error(String(error ?? "Not authenticated"));
      return data;
    },
  });

  // Demo mode keeps the theme toggle below but drops the auth block; the normal
  // flow still hides the whole menu on auth pages or before the user loads.
  if (!DEMO_MODE && (onAuthPage || !user)) return null;

  const onSignOut = async () => {
    if (signingOut) return;
    setSigningOut(true);
    const ok = await performSignOut({
      logout: () => api.POST("/api/auth/logout"),
      clearAuthState: () => queryClient.clear(),
      redirect: (to) => window.location.assign(to),
      onError: (message) => toast.error(message),
    });
    // on success we're navigating away; only re-enable if logout failed
    if (!ok) setSigningOut(false);
  };

  return (
    <div className="flex items-center gap-3">
      {/* class-based toggle over the existing .dark token set; no provider/persistence */}
      <button
        type="button"
        onClick={() => {
          const isDark = document.documentElement.classList.toggle("dark");
          try {
            localStorage.setItem("atip-theme", isDark ? "dark" : "light");
          } catch {}
        }}
        className="inline-flex size-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        aria-label="Toggle dark mode"
      >
        <Moon className="size-4 dark:hidden" />
        <Sun className="hidden size-4 dark:inline" />
      </button>
      {!DEMO_MODE && user && (
        <>
          <span className="hidden text-sm text-muted-foreground sm:inline" title={user.email}>
            {user.display_name}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={onSignOut}
            disabled={signingOut}
            aria-label="Sign out"
            aria-busy={signingOut}
          >
            {signingOut ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <LogOut className="size-3.5" />
            )}
            Sign out
          </Button>
        </>
      )}
    </div>
  );
}
