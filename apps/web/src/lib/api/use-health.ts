"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "./client";
import type { HealthResponse } from "./types";

async function fetchHealth(): Promise<HealthResponse> {
  const { data, error, response } = await api.GET("/health");
  if (data) return data;
  // a degraded backend answers 503 with the same payload shape
  if (response.status === 503 && error) return error as HealthResponse;
  throw new Error("API unreachable");
}

/** Shared backend health/capability state (header tray, AI-control gating). */
export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
  });
}

/**
 * Whether answer generation / evidence extraction is available.
 * `undefined` while health is unknown — callers should stay enabled rather
 * than flash a disabled state during the first load.
 */
export function useGenerationEnabled(): boolean | undefined {
  const { data } = useHealth();
  return data?.generation_enabled;
}
