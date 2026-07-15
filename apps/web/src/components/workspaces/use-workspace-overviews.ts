"use client";

import { useQueries, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { api } from "@/lib/api/client";
import type { Document, Workspace } from "@/lib/api/types";

/** Per-workspace document rollup for cards and dashboard KPIs. */
export interface WorkspaceOverview {
  documentCount: number;
  pageCount: number;
  readyCount: number;
  processingCount: number;
  failedCount: number;
  /** Most recent document upload, falling back to workspace creation. */
  updatedAt: string;
}

export interface DashboardTotals {
  workspaces: number;
  documents: number;
  pages: number;
  ready: number;
  processing: number;
  failed: number;
}

function rollup(workspace: Workspace, documents: Document[]): WorkspaceOverview {
  const updatedAt = documents.reduce(
    (latest, document) => (document.created_at > latest ? document.created_at : latest),
    workspace.created_at,
  );
  return {
    documentCount: documents.length,
    pageCount: documents.reduce((sum, document) => sum + (document.page_count ?? 0), 0),
    readyCount: documents.filter((document) => document.status === "READY").length,
    processingCount: documents.filter(
      (document) => document.status === "PENDING" || document.status === "PROCESSING",
    ).length,
    failedCount: documents.filter((document) => document.status === "FAILED").length,
    updatedAt,
  };
}

/**
 * Workspaces plus a per-workspace document rollup. The document queries share
 * the ["documents", id] cache with the workspace detail page, so navigating
 * into a workspace reuses what the dashboard already fetched.
 */
export function useWorkspaceOverviews() {
  const workspacesQuery = useQuery({
    queryKey: ["workspaces"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/workspaces");
      if (!data) throw new Error(String(error ?? "Failed to load workspaces"));
      return data;
    },
  });

  const workspaces = useMemo(() => workspacesQuery.data ?? [], [workspacesQuery.data]);

  const documentQueries = useQueries({
    queries: workspaces.map((workspace) => ({
      queryKey: ["documents", workspace.id],
      queryFn: async () => {
        const { data, error } = await api.GET("/api/workspaces/{workspace_id}/documents", {
          params: { path: { workspace_id: workspace.id } },
        });
        if (!data) throw new Error(String(error ?? "Failed to load documents"));
        return data;
      },
      staleTime: 15_000,
    })),
  });

  const overviews = useMemo(() => {
    const byId = new Map<string, WorkspaceOverview>();
    workspaces.forEach((workspace, index) => {
      const documents = documentQueries[index]?.data;
      if (documents) byId.set(workspace.id, rollup(workspace, documents));
    });
    return byId;
  }, [workspaces, documentQueries]);

  const totals: DashboardTotals | null = useMemo(() => {
    // totals only once every workspace has reported, so KPIs never undercount
    if (!workspacesQuery.data || overviews.size !== workspaces.length) return null;
    const all = [...overviews.values()];
    return {
      workspaces: workspaces.length,
      documents: all.reduce((sum, o) => sum + o.documentCount, 0),
      pages: all.reduce((sum, o) => sum + o.pageCount, 0),
      ready: all.reduce((sum, o) => sum + o.readyCount, 0),
      processing: all.reduce((sum, o) => sum + o.processingCount, 0),
      failed: all.reduce((sum, o) => sum + o.failedCount, 0),
    };
  }, [workspacesQuery.data, workspaces, overviews]);

  return {
    workspaces,
    overviews,
    totals,
    isPending: workspacesQuery.isPending,
    isError: workspacesQuery.isError,
    refetch: workspacesQuery.refetch,
  };
}
