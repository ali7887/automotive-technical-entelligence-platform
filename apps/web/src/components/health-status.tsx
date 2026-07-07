"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import type { HealthResponse } from "@/lib/api/types";
import { cn } from "@/lib/utils";

async function fetchHealth(): Promise<HealthResponse> {
  const { data, error, response } = await api.GET("/health");
  if (data) return data;
  // a degraded backend answers 503 with the same payload shape
  if (response.status === 503 && error) return error as HealthResponse;
  throw new Error("API unreachable");
}

export function HealthStatus() {
  const { data, isPending, isError } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
  });

  const state = isPending ? "checking" : isError ? "offline" : data?.status === "ok" ? "ok" : "degraded";

  const label = {
    checking: "Checking API…",
    offline: "API offline",
    degraded: "Services degraded",
    ok: "All systems go",
  }[state];

  const failing =
    data && data.status !== "ok"
      ? Object.entries(data.services)
          .filter(([, service]) => service.status !== "ok")
          .map(([name]) => name)
          .join(", ")
      : null;

  return (
    <div
      className="flex items-center gap-2 text-sm text-muted-foreground"
      title={failing ? `Failing: ${failing}` : undefined}
    >
      <span
        className={cn("size-2 rounded-full", {
          "bg-emerald-500": state === "ok",
          "bg-amber-500": state === "degraded",
          "bg-red-500": state === "offline",
          "bg-muted-foreground/50 animate-pulse": state === "checking",
        })}
      />
      {label}
    </div>
  );
}
