"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ChatPanel } from "@/components/chat/chat-panel";
import { DocumentsTable } from "@/components/documents/documents-table";
import { JobWatchers } from "@/components/documents/job-watcher";
import { UploadButton } from "@/components/documents/upload-button";
import { EvidenceMapPanel } from "@/components/evidence/evidence-map-panel";
import { EvidenceViewerPanel } from "@/components/pdf/evidence-viewer-panel";
import { ReviewQueuePanel } from "@/components/review/review-queue-panel";
import { SearchPanel } from "@/components/search/search-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { TabList, TabPanel } from "@/components/ui/tabs";
import { api } from "@/lib/api/client";
import { formatDate } from "@/lib/format";

const WORKSPACE_TABS = ["documents", "ask", "evidence", "review", "search"] as const;
type WorkspaceTab = (typeof WORKSPACE_TABS)[number];

function isWorkspaceTab(value: string | undefined): value is WorkspaceTab {
  return (WORKSPACE_TABS as readonly string[]).includes(value ?? "");
}

export function WorkspaceDetail({
  workspaceId,
  initialTab,
  initialQuestion,
}: {
  workspaceId: string;
  /** e.g. `?tab=ask` from dashboard card actions; invalid values fall back to documents */
  initialTab?: string;
  initialQuestion?: string;
}) {
  const [tab, setTab] = useState<WorkspaceTab>(
    isWorkspaceTab(initialTab) ? initialTab : "documents",
  );

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

  // shared with the panels below via the ["documents", id] cache
  const { data: documents } = useQuery({
    queryKey: ["documents", workspaceId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/workspaces/{workspace_id}/documents", {
        params: { path: { workspace_id: workspaceId } },
      });
      if (!data) throw new Error(String(error ?? "Failed to load documents"));
      return data;
    },
  });

  const { data: evidence } = useQuery({
    queryKey: ["evidence", workspaceId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/workspaces/{workspace_id}/evidence", {
        params: { path: { workspace_id: workspaceId } },
      });
      if (!data) throw new Error(String(error ?? "Failed to load evidence"));
      return data;
    },
  });

  if (isError) {
    return (
      <EmptyState
        title="Workspace not found"
        description="It may have been deleted, or the link is out of date."
        action={
          <Button variant="outline" nativeButton={false} render={<Link href="/" />}>
            Back to dashboard
          </Button>
        }
      />
    );
  }

  const pageCount = documents?.reduce((sum, d) => sum + (d.page_count ?? 0), 0) ?? 0;
  const processingCount =
    documents?.filter((d) => d.status === "PENDING" || d.status === "PROCESSING").length ?? 0;
  const failedCount = documents?.filter((d) => d.status === "FAILED").length ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <Link
            href="/"
            className="mb-1 inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="size-3.5" /> Dashboard
          </Link>
          {isPending ? (
            <Skeleton className="h-8 w-64" />
          ) : (
            <h1 className="truncate text-2xl font-semibold tracking-tight">{workspace.name}</h1>
          )}
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            {workspace && <span>Created {formatDate(workspace.created_at)}</span>}
            {documents && (
              <span className="tabular-nums">
                {documents.length} document{documents.length === 1 ? "" : "s"}
                {pageCount > 0 && <> · {pageCount.toLocaleString()} pages</>}
              </span>
            )}
            {failedCount > 0 && (
              <Badge variant="destructive">{failedCount} failed</Badge>
            )}
            {processingCount > 0 && (
              <Badge variant="warning">Processing {processingCount}</Badge>
            )}
          </div>
        </div>
        <UploadButton workspaceId={workspaceId} />
      </div>

      <TabList
        items={[
          { id: "documents", label: "Documents", count: documents?.length },
          { id: "ask", label: "Ask AI" },
          { id: "evidence", label: "Evidence Map", count: evidence?.length },
          { id: "review", label: "Review Queue" },
          { id: "search", label: "Search" },
        ]}
        value={tab}
        onChange={(id) => setTab(id as WorkspaceTab)}
      />

      {/* panels stay mounted so chat threads and filters survive tab switches */}
      <TabPanel id="documents" active={tab === "documents"}>
        <section className="space-y-4">
          <div>
            <h2 className="text-lg font-semibold tracking-tight">Documents</h2>
            <p className="text-sm text-muted-foreground">
              Source PDFs with page-level citations for verified evidence retrieval.
            </p>
          </div>
          <DocumentsTable workspaceId={workspaceId} />
        </section>
      </TabPanel>
      <TabPanel id="ask" active={tab === "ask"}>
        <ChatPanel workspaceId={workspaceId} initialQuestion={initialQuestion} />
      </TabPanel>
      <TabPanel id="evidence" active={tab === "evidence"}>
        <EvidenceMapPanel workspaceId={workspaceId} />
      </TabPanel>
      <TabPanel id="review" active={tab === "review"}>
        <ReviewQueuePanel workspaceId={workspaceId} />
      </TabPanel>
      <TabPanel id="search" active={tab === "search"}>
        <SearchPanel workspaceId={workspaceId} />
      </TabPanel>

      <JobWatchers workspaceId={workspaceId} />
      <EvidenceViewerPanel />
    </div>
  );
}
