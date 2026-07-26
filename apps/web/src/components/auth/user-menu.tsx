"use client";

import { useQuery } from "@tanstack/react-query";
import { Moon, Sun } from "lucide-react";

import { api } from "@/lib/api/client";
import type { User } from "@/lib/api/types";

/**
 * Header identity + theme toggle. Authentication has been removed, so there is
 * no sign-in/sign-out: every request runs as the default admin, and /api/auth/me
 * always returns that account. The name is shown for context only.
 */
export function UserMenu() {
  const { data: user } = useQuery<User>({
    queryKey: ["auth", "me"],
    retry: false,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/auth/me");
      if (!data) throw new Error(String(error ?? "Failed to load user"));
      return data;
    },
  });

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
      {user && (
        <span className="hidden text-sm text-muted-foreground sm:inline" title={user.email}>
          {user.display_name}
        </span>
      )}
    </div>
  );
}
