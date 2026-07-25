import { describe, expect, it } from "vitest";

import type { HealthResponse } from "./api/types";
import { deriveHealthBanner, INFRA_UP_HINT } from "./health-banner";

function health(overrides: Partial<HealthResponse> = {}): HealthResponse {
  return {
    status: "degraded",
    version: "test",
    generation_enabled: false,
    services: {
      postgres: { status: "error", detail: "connection refused" },
      redis: { status: "ok" },
      qdrant: { status: "ok" },
    },
    ...overrides,
  };
}

describe("deriveHealthBanner", () => {
  it("names the failing service when the backend is degraded", () => {
    const banner = deriveHealthBanner({
      isPending: false,
      isError: false,
      data: health(),
      isDevelopment: false,
    });
    expect(banner.state).toBe("degraded");
    expect(banner.failingServices).toEqual(["postgres"]);
    expect(banner.serviceDetails).toContain("postgres: connection refused");
  });

  it("falls back to the status when a failing service reports no detail", () => {
    const banner = deriveHealthBanner({
      isPending: false,
      isError: false,
      data: health({
        services: {
          postgres: { status: "ok" },
          redis: { status: "error" },
          qdrant: { status: "ok" },
        },
      }),
      isDevelopment: false,
    });
    expect(banner.failingServices).toEqual(["redis"]);
    expect(banner.serviceDetails).toEqual(["redis: error"]);
  });

  it("joins multiple failing services deterministically in services order", () => {
    const banner = deriveHealthBanner({
      isPending: false,
      isError: false,
      data: health({
        services: {
          postgres: { status: "error", detail: "connection refused" },
          redis: { status: "error" },
          qdrant: { status: "ok" },
        },
      }),
      isDevelopment: false,
    });
    expect(banner.failingServices).toEqual(["postgres", "redis"]);
    expect(banner.serviceDetails).toEqual([
      "postgres: connection refused",
      "redis: error",
    ]);
  });

  it("surfaces the infra:up hint only in a development build", () => {
    const base = { isPending: false, isError: false, data: health() } as const;
    expect(deriveHealthBanner({ ...base, isDevelopment: true }).devHint).toBe(INFRA_UP_HINT);
    expect(deriveHealthBanner({ ...base, isDevelopment: false }).devHint).toBeNull();
  });

  it("withholds the hint when the API is fully offline (starting data stores can't fix it)", () => {
    const banner = deriveHealthBanner({
      isPending: false,
      isError: true,
      data: undefined,
      isDevelopment: true,
    });
    expect(banner.state).toBe("offline");
    expect(banner.failingServices).toEqual([]);
    expect(banner.devHint).toBeNull();
  });

  it("reports healthy and checking states with no failing services or hint", () => {
    const ok = deriveHealthBanner({
      isPending: false,
      isError: false,
      data: health({
        status: "ok",
        services: {
          postgres: { status: "ok" },
          redis: { status: "ok" },
          qdrant: { status: "ok" },
        },
      }),
      isDevelopment: true,
    });
    expect(ok.state).toBe("ok");
    expect(ok.failingServices).toEqual([]);
    expect(ok.devHint).toBeNull();

    const pending = deriveHealthBanner({
      isPending: true,
      isError: false,
      data: undefined,
      isDevelopment: true,
    });
    expect(pending.state).toBe("checking");
    expect(pending.label).toBe("Checking…");
  });
});
