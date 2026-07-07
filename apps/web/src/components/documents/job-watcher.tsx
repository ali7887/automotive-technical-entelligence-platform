"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { toast } from "sonner";

import { api } from "@/lib/api/client";
import { useUploadTracker } from "@/lib/store";

/** Polls one processing job until it settles, then toasts the outcome. */
function JobWatcher({
  documentId,
  jobId,
  workspaceId,
}: {
  documentId: string;
  jobId: string;
  workspaceId: string;
}) {
  const queryClient = useQueryClient();
  const untrackJob = useUploadTracker((state) => state.untrackJob);

  const { data: job } = useQuery({
    queryKey: ["job", jobId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/jobs/{job_id}", {
        params: { path: { job_id: jobId } },
      });
      if (!data) throw new Error(String(error ?? "Failed to load job"));
      return data;
    },
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "READY" || status === "FAILED" ? false : 1500;
    },
  });

  useEffect(() => {
    if (!job) return;
    if (job.status === "READY") {
      toast.success("Document processed and ready");
    } else if (job.status === "FAILED") {
      toast.error(job.error_message ?? "Document processing failed");
    } else {
      return;
    }
    untrackJob(documentId);
    queryClient.invalidateQueries({ queryKey: ["documents", workspaceId] });
  }, [job, documentId, workspaceId, queryClient, untrackJob]);

  return null;
}

export function JobWatchers({ workspaceId }: { workspaceId: string }) {
  const activeJobs = useUploadTracker((state) => state.activeJobs);
  return (
    <>
      {Object.entries(activeJobs).map(([documentId, jobId]) => (
        <JobWatcher
          key={jobId}
          documentId={documentId}
          jobId={jobId}
          workspaceId={workspaceId}
        />
      ))}
    </>
  );
}
