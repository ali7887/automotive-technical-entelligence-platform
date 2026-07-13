import type { EvidenceRisk, ReviewStatus } from "@/lib/api/types";
import type { components } from "@/lib/api/schema";

type ReviewAction = components["schemas"]["ReviewAction"];

export const REVIEW_STATUS_LABELS: Record<ReviewStatus, string> = {
  NEW: "New",
  IN_REVIEW: "In review",
  APPROVED: "Approved",
  REJECTED: "Rejected",
  NEEDS_REVISION: "Needs revision",
};

/** Badge tint per review status; pairs with the outline badge variant. */
export const REVIEW_STATUS_CLASSES: Record<ReviewStatus, string> = {
  NEW: "border-border text-muted-foreground",
  IN_REVIEW: "border-blue-500/50 text-blue-600 dark:text-blue-400",
  APPROVED: "border-emerald-500/50 text-emerald-600 dark:text-emerald-400",
  REJECTED: "border-red-500/50 text-red-600 dark:text-red-400",
  NEEDS_REVISION: "border-amber-500/50 text-amber-600 dark:text-amber-400",
};

export const REVIEW_ACTION_LABELS: Record<ReviewAction, string> = {
  START_REVIEW: "Started review",
  APPROVE: "Approved",
  REJECT: "Rejected",
  REQUEST_REVISION: "Requested revision",
  COMMENT: "Commented",
  SET_RISK: "Set risk",
  SET_STATUS: "Set compliance status",
  EXTRACTION_ARCHIVED: "Archived by re-extraction",
};

export const RISK_LABELS: Record<EvidenceRisk, string> = {
  UNRATED: "Unrated",
  LOW: "Low",
  MEDIUM: "Medium",
  HIGH: "High",
};

export const RISK_TEXT_CLASSES: Record<EvidenceRisk, string> = {
  UNRATED: "text-muted-foreground",
  LOW: "text-emerald-600 dark:text-emerald-500",
  MEDIUM: "text-amber-600 dark:text-amber-500",
  HIGH: "text-red-600 dark:text-red-500",
};
