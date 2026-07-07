import type { components } from "./schema";

export type Workspace = components["schemas"]["WorkspaceRead"];
export type Document = components["schemas"]["DocumentRead"];
export type ProcessingJob = components["schemas"]["JobRead"];
export type DocumentUploadResponse = components["schemas"]["DocumentUploadResponse"];
export type HealthResponse = components["schemas"]["HealthResponse"];
export type DocumentStatus = components["schemas"]["DocumentStatus"];
export type JobStatus = components["schemas"]["JobStatus"];

export interface ApiError {
  code: string;
  message: string;
}

export function errorMessage(error: unknown, fallback: string): string {
  if (error && typeof error === "object" && "message" in error) {
    return String((error as ApiError).message);
  }
  return fallback;
}
