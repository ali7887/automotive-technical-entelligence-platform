"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import { ChatPanel } from "@/components/chat/chat-panel";
import { DocumentsTable } from "@/components/documents/documents-table";
import { JobWatchers } from "@/components/documents/job-watcher";
import { UploadButton } from "@/components/documents/upload-button";
import { EvidenceMapPanel } from "@/components/evidence/evidence-map-panel";
import { EvidenceViewerPanel } from "@/components/pdf/evidence-viewer-panel";
import { ReviewQueuePanel } from "@/components/review/review-queue-panel";
import { SearchPanel } from "@/components/search/search-panel";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api/client";

export function WorkspaceDetail({ workspaceId }: { workspaceId: string }) {
  const { data: workspace, isPending, isError } = useQuery({
    queryKey: ["workspaces", workspaceId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/workspaces/{workspace_id}", {
        params: { path: { workspace_id: workspaceId } },
      });
      if (!data) throw new Error(String(error ?? "Failed to load workspace"));
      return data;
    },
  });

  if (isError) {
    return (
      <div className="rounded-xl border border-dashed p-10 text-center">
        <p className="font-medium">Workspace not found</p>
        <Button variant="outline" className="mt-4" render={<Link href="/" />}>
          Back to workspaces
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <Link
            href="/"
            className="mb-1 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="size-3.5" /> Workspaces
          </Link>
          {isPending ? (
            <Skeleton className="h-8 w-64" />
          ) : (
            <h1 className="truncate text-2xl font-semibold tracking-tight">{workspace.name}</h1>
          )}
        </div>
        <UploadButton workspaceId={workspaceId} />
      </div>
      <DocumentsTable workspaceId={workspaceId} />
      <ChatPanel workspaceId={workspaceId} />
      <EvidenceMapPanel workspaceId={workspaceId} />
      <ReviewQueuePanel workspaceId={workspaceId} />
      <SearchPanel workspaceId={workspaceId} />
      <JobWatchers workspaceId={workspaceId} />
      <EvidenceViewerPanel />
    </div>
  );
}
