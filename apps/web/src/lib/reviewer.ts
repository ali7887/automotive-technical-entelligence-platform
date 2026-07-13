const REVIEWER_STORAGE_KEY = "atip-reviewer-name";

/** Reviewer display name persisted locally; audit events record it as actor_name. */
export function loadReviewerName(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(REVIEWER_STORAGE_KEY) ?? "";
}

export function saveReviewerName(name: string): void {
  window.localStorage.setItem(REVIEWER_STORAGE_KEY, name.trim());
}

export function reviewerOrAnonymous(name: string): string {
  return name.trim() || "anonymous";
}
