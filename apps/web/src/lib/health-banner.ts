import type { HealthResponse } from "@/lib/api/types";

/** Discrete banner states derived from the health query. */
export type HealthState = "checking" | "offline" | "degraded" | "ok";

export interface HealthBanner {
  state: HealthState;
  label: string;
  /** Backend dependencies currently reporting an error. Empty unless `state` is "degraded". */
  failingServices: string[];
  /** `name: detail` lines for the tooltip. Empty unless `state` is "degraded". */
  serviceDetails: string[];
  /**
   * Actionable hint for a local checkout, or null. Set only when a dependency is
   * down (`state === "degraded"`) in a development build — never in production
   * (managed data stores aren't started with docker compose), and never for a
   * fully offline API, which starting the data stores cannot revive.
   */
  devHint: string | null;
}

const STATE_LABELS: Record<HealthState, string> = {
  checking: "Checking…",
  offline: "API offline",
  degraded: "Degraded",
  ok: "Operational",
};

/** The exact command that starts the local docker stack (see the root `infra:up` script). */
export const INFRA_UP_HINT = "run pnpm infra:up";

export function deriveHealthBanner(input: {
  isPending: boolean;
  isError: boolean;
  data: HealthResponse | undefined;
  isDevelopment: boolean;
}): HealthBanner {
  const { isPending, isError, data, isDevelopment } = input;

  const state: HealthState = isPending
    ? "checking"
    : isError
      ? "offline"
      : data?.status === "ok"
        ? "ok"
        : "degraded";

  // A degraded payload names which dependency failed; "offline" means the API
  // itself never answered, so there is no per-service breakdown to show.
  const failing =
    state === "degraded" && data
      ? Object.entries(data.services).filter(([, service]) => service.status !== "ok")
      : [];

  return {
    state,
    label: STATE_LABELS[state],
    failingServices: failing.map(([name]) => name),
    serviceDetails: failing.map(([name, service]) => `${name}: ${service.detail ?? service.status}`),
    devHint: isDevelopment && state === "degraded" ? INFRA_UP_HINT : null,
  };
}
