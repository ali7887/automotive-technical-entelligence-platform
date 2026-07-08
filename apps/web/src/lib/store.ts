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

/** A citation location to show in the PDF evidence viewer. */
export interface EvidenceTarget {
  documentId: string;
  documentName: string;
  page: number;
  /** Verified quote (or chunk excerpt) to highlight via the PDF text layer. */
  quote?: string;
  clauseId?: string | null;
}

interface EvidenceViewerState {
  target: EvidenceTarget | null;
  openEvidence: (target: EvidenceTarget) => void;
  closeEvidence: () => void;
}

export const useEvidenceViewer = create<EvidenceViewerState>((set) => ({
  target: null,
  openEvidence: (target) => set({ target }),
  closeEvidence: () => set({ target: null }),
}));
