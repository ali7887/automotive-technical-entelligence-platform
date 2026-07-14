"use client";

import { useQuery } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";
import type { User } from "@/lib/api/types";

/** Current user + sign-out, shown in the header on authenticated pages. */
export function UserMenu() {
  const pathname = usePathname();
  const onLoginPage = pathname === "/login";

  const { data: user } = useQuery<User>({
    queryKey: ["auth", "me"],
    enabled: !onLoginPage,
    retry: false,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/auth/me");
      if (!data) throw new Error(String(error ?? "Not authenticated"));
      return data;
    },
  });

  if (onLoginPage || !user) return null;

  const logout = async () => {
    await api.POST("/api/auth/logout");
    window.location.assign("/login");
  };

  return (
    <div className="flex items-center gap-3">
      <span className="hidden text-sm text-muted-foreground sm:inline" title={user.email}>
        {user.display_name}
      </span>
      <Button variant="outline" size="sm" onClick={logout} aria-label="Sign out">
        <LogOut className="size-3.5" />
        Sign out
      </Button>
    </div>
  );
}
