"use client";

import { useQuery } from "@tanstack/react-query";
import { FileText } from "lucide-react";

import { StatusBadge } from "@/components/documents/status-badge";
import { UploadButton } from "@/components/documents/upload-button";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";

export function DocumentsTable({ workspaceId }: { workspaceId: string }) {
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["documents", workspaceId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/workspaces/{workspace_id}/documents", {
        params: { path: { workspace_id: workspaceId } },
      });
      if (!data) throw new Error(String(error ?? "Failed to load documents"));
      return data;
    },
    // keep polling while anything is still being processed
    refetchInterval: (query) =>
      query.state.data?.some(
        (document) => document.status === "PENDING" || document.status === "PROCESSING",
      )
        ? 2000
        : false,
  });

  if (isPending) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-12 rounded-lg" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <EmptyState
        variant="error"
        title="Could not load documents"
        description="Check that the API is reachable, then try again."
        action={
          <Button variant="outline" onClick={() => refetch()}>
            Retry
          </Button>
        }
      />
    );
  }

  if (data.length === 0) {
    return (
      <EmptyState
        icon={FileText}
        title="No documents yet"
        description="Upload a regulation or standard PDF — it is chunked clause by clause with page provenance, ready for search, questions, and evidence extraction."
        action={<UploadButton workspaceId={workspaceId} />}
      />
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border bg-card shadow-2xs">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Pages</TableHead>
            <TableHead className="text-right">Uploaded</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((document) => (
            <TableRow key={document.id}>
              <TableCell className="max-w-96 truncate font-medium">{document.name}</TableCell>
              <TableCell>
                <StatusBadge status={document.status} />
              </TableCell>
              <TableCell className="text-right font-mono text-xs tabular-nums text-muted-foreground">
                {document.page_count ?? "—"}
              </TableCell>
              <TableCell className="text-right text-xs tabular-nums text-muted-foreground">
                {formatDateTime(document.created_at)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
