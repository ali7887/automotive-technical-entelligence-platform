"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import { useRef } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";
import { errorMessage, type DocumentUploadResponse } from "@/lib/api/types";
import { useUploadTracker } from "@/lib/store";

export function UploadButton({ workspaceId }: { workspaceId: string }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();
  const trackJob = useUploadTracker((state) => state.trackJob);

  const mutation = useMutation({
    mutationFn: async (file: File): Promise<DocumentUploadResponse> => {
      const { data, error } = await api.POST("/api/workspaces/{workspace_id}/documents", {
        params: { path: { workspace_id: workspaceId } },
        // openapi-fetch types multipart bodies as string; hand it a real FormData
        body: { file: file as unknown as string },
        bodySerializer: () => {
          const formData = new FormData();
          formData.append("file", file);
          return formData;
        },
      });
      if (!data) throw new Error(errorMessage(error, "Upload failed"));
      return data;
    },
    onSuccess: ({ document, job }) => {
      // 202 Accepted: the JobWatcher advances this toast through the stages
      toast.loading(`Processing “${document.name}”…`, { id: job.id });
      trackJob(document.id, job.id);
      queryClient.invalidateQueries({ queryKey: ["documents", workspaceId] });
    },
    onError: (error) => toast.error(error.message),
  });

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) mutation.mutate(file);
          event.target.value = "";
        }}
      />
      <Button onClick={() => inputRef.current?.click()} disabled={mutation.isPending}>
        <Upload className="size-4" />
        {mutation.isPending ? "Uploading…" : "Upload PDF"}
      </Button>
    </>
  );
}
