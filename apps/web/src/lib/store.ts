import { create } from "zustand";

/** Jobs still being polled after an upload, keyed by document id. */
interface UploadTrackerState {
  activeJobs: Record<string, string>;
  trackJob: (documentId: string, jobId: string) => void;
  untrackJob: (documentId: string) => void;
}

export const useUploadTracker = create<UploadTrackerState>((set) => ({
  activeJobs: {},
  trackJob: (documentId, jobId) =>
    set((state) => ({ activeJobs: { ...state.activeJobs, [documentId]: jobId } })),
  untrackJob: (documentId) =>
    set((state) => {
      const rest = { ...state.activeJobs };
      delete rest[documentId];
      return { activeJobs: rest };
    }),
}));
