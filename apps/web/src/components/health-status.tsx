"use client";

import { useHealth } from "@/lib/api/use-health";
import { cn } from "@/lib/utils";

/** Header status tray: backend health as a compact, structured chip. */
export function HealthStatus() {
  const { data, isPending, isError } = useHealth();

  const state = isPending ? "checking" : isError ? "offline" : data?.status === "ok" ? "ok" : "degraded";

  const label = {
    checking: "Checking…",
    offline: "API offline",
    degraded: "Degraded",
    ok: "Operational",
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
      className="flex h-7 items-center gap-2 rounded-lg border bg-card px-2.5 text-xs text-muted-foreground"
      title={failing ? `Failing: ${failing}` : "Backend service health"}
    >
      <span
        className={cn("size-1.5 rounded-full", {
          "bg-success": state === "ok",
          "bg-warning": state === "degraded",
          "bg-destructive": state === "offline",
          "bg-muted-foreground/50 animate-pulse": state === "checking",
        })}
      />
      {label}
    </div>
  );
}
