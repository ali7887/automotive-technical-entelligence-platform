"use client";

import { useQuery } from "@tanstack/react-query";

import { StatusBadge } from "@/components/documents/status-badge";
import { Button } from "@/components/ui/button";
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
      <div className="rounded-xl border border-dashed p-10 text-center">
        <p className="font-medium">Could not load documents</p>
        <Button variant="outline" className="mt-4" onClick={() => refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="rounded-xl border border-dashed p-10 text-center">
        <p className="font-medium">No documents yet</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Upload a regulation or standard PDF to get started.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border">
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
              <TableCell className="text-right tabular-nums">
                {document.page_count ?? "—"}
              </TableCell>
              <TableCell className="text-right text-muted-foreground">
                {new Date(document.created_at).toLocaleString()}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
