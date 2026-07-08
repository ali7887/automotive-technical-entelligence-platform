import type { components } from "./schema";

export type Workspace = components["schemas"]["WorkspaceRead"];
export type Document = components["schemas"]["DocumentRead"];
export type ProcessingJob = components["schemas"]["JobRead"];
export type DocumentUploadResponse = components["schemas"]["DocumentUploadResponse"];
export type HealthResponse = components["schemas"]["HealthResponse"];
export type DocumentStatus = components["schemas"]["DocumentStatus"];
export type JobStatus = components["schemas"]["JobStatus"];
export type SearchResponse = components["schemas"]["SearchResponse"];
export type SearchResult = components["schemas"]["SearchResult"];
export type AskResponse = components["schemas"]["AskResponse"];
export type Citation = components["schemas"]["Citation"];
export type RetrievedSource = components["schemas"]["RetrievedSourceRead"];
export type EvidenceItem = components["schemas"]["EvidenceItemRead"];
export type EvidenceCitation = components["schemas"]["EvidenceCitationRead"];
export type EvidenceStatus = components["schemas"]["EvidenceStatus"];
export type EvidenceRisk = components["schemas"]["EvidenceRisk"];
export type EvidenceExtractResponse = components["schemas"]["EvidenceExtractResponse"];
export type EvidenceMapExport = components["schemas"]["EvidenceMapExport"];

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
