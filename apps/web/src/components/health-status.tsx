"use client";

import { useHealth } from "@/lib/api/use-health";
import { deriveHealthBanner } from "@/lib/health-banner";
import { cn } from "@/lib/utils";

// Statically inlined by the bundler at build time; in a production build this is
// always false, so the local docker hint is never rendered for production users.
const isDevelopment = process.env.NODE_ENV === "development";

/** Header status tray: backend health as a compact, structured chip. */
export function HealthStatus() {
  const { data, isPending, isError } = useHealth();
  const { state, label, failingServices, serviceDetails, devHint } = deriveHealthBanner({
    isPending,
    isError,
    data,
    isDevelopment,
  });

  const title =
    state === "offline"
      ? "Backend API unreachable"
      : serviceDetails.length
        ? [
            serviceDetails.join("\n"),
            devHint ? `Local dev: ${devHint} to start Postgres, Redis, and Qdrant.` : null,
          ]
            .filter(Boolean)
            .join("\n\n")
        : "Backend service health";

  return (
    <div
      className="flex h-7 items-center gap-2 rounded-lg border bg-card px-2.5 text-xs text-muted-foreground"
      title={title}
    >
      <span
        className={cn("size-1.5 rounded-full", {
          "bg-success": state === "ok",
          "bg-warning": state === "degraded",
          "bg-destructive": state === "offline",
          "bg-muted-foreground/50 animate-pulse": state === "checking",
        })}
      />
      <span>{label}</span>
      {failingServices.length > 0 && (
        <span className="text-muted-foreground/70">· {failingServices.join(", ")}</span>
      )}
      {devHint && <span className="font-medium text-warning">— {devHint}</span>}
    </div>
  );
}
