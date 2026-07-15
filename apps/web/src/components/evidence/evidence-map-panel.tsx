"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileSearch, Loader2, ScanSearch } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, API_BASE_URL } from "@/lib/api/client";
import type { EvidenceItem, EvidenceRisk, EvidenceStatus } from "@/lib/api/types";
import { errorMessage } from "@/lib/api/types";
import { useGenerationEnabled } from "@/lib/api/use-health";
import { loadReviewerName, reviewerOrAnonymous } from "@/lib/reviewer";
import { useEvidenceViewer } from "@/lib/store";
import { cn } from "@/lib/utils";

const STATUS_OPTIONS: { value: EvidenceStatus; label: string }[] = [
  { value: "OPEN", label: "Open" },
  { value: "IN_REVIEW", label: "In review" },
  { value: "COMPLIANT", label: "Compliant" },
  { value: "NON_COMPLIANT", label: "Non-compliant" },
  { value: "NOT_APPLICABLE", label: "Not applicable" },
];

const RISK_OPTIONS: { value: EvidenceRisk; label: string }[] = [
  { value: "UNRATED", label: "Unrated" },
  { value: "LOW", label: "Low" },
  { value: "MEDIUM", label: "Medium" },
  { value: "HIGH", label: "High" },
];

const RISK_CLASSES: Record<EvidenceRisk, string> = {
  UNRATED: "",
  LOW: "text-success-strong",
  MEDIUM: "text-warning-strong",
  HIGH: "text-destructive-strong",
};

export function EvidenceMapPanel({ workspaceId }: { workspaceId: string }) {
  const queryClient = useQueryClient();
  const [documentId, setDocumentId] = useState("");
  const [includeHistory, setIncludeHistory] = useState(false);
  const openEvidence = useEvidenceViewer((state) => state.openEvidence);
  // extraction runs through the LLM, so it is disabled without a configured key
  const generationOff = useGenerationEnabled() === false;

  const { data: documents } = useQuery({
    queryKey: ["documents", workspaceId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/workspaces/{workspace_id}/documents", {
        params: { path: { workspace_id: workspaceId } },
      });
      if (!data) throw new Error(errorMessage(error, "Failed to load documents"));
      return data;
    },
  });
  const readyDocuments = documents?.filter((document) => document.status === "READY") ?? [];

  const {
    data: items,
    isPending,
    isError,
  } = useQuery({
    queryKey: ["evidence", workspaceId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/workspaces/{workspace_id}/evidence", {
        params: { path: { workspace_id: workspaceId } },
      });
      if (!data) throw new Error(errorMessage(error, "Failed to load evidence"));
      return data;
    },
  });

  const extract = useMutation({
    mutationFn: async (targetDocumentId: string) => {
      const { data, error } = await api.POST("/api/documents/{document_id}/evidence/extract", {
        params: { path: { document_id: targetDocumentId } },
      });
      if (!data) throw new Error(errorMessage(error, "Extraction failed"));
      return data;
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["evidence", workspaceId] });
      queryClient.invalidateQueries({ queryKey: ["review-queue"] });
      const dropped = result.requirements_dropped
        ? ` (${result.requirements_dropped} without verifiable evidence dropped)`
        : "";
      toast.success(`Extracted ${result.items.length} verified requirement${result.items.length === 1 ? "" : "s"}${dropped}`);
      if (result.items_archived > 0) {
        toast.info(
          `${result.items_archived} reviewed item${result.items_archived === 1 ? "" : "s"} archived with history preserved`,
        );
      }
    },
    onError: (error) => toast.error(error.message),
  });

  const update = useMutation({
    mutationFn: async (input: {
      itemId: string;
      version: number;
      patch: { status?: EvidenceStatus; risk?: EvidenceRisk };
    }) => {
      const { data, error } = await api.PATCH("/api/evidence/{item_id}", {
        params: { path: { item_id: input.itemId } },
        // inline edits are audited; record who made them and which version of
        // the row they were looking at (optimistic lock)
        body: {
          ...input.patch,
          actor_name: reviewerOrAnonymous(loadReviewerName()),
          expected_version: input.version,
        },
      });
      if (!data) {
        const failure = new Error(errorMessage(error, "Update failed")) as Error & {
          code?: string;
        };
        failure.code = (error as { code?: string } | undefined)?.code;
        throw failure;
      }
      return data;
    },
    onSuccess: (updated) => {
      queryClient.setQueryData<EvidenceItem[]>(["evidence", workspaceId], (current) =>
        current?.map((item) => (item.id === updated.id ? updated : item)),
      );
      // inline edits append audit events, so queue rows and histories change too
      queryClient.invalidateQueries({ queryKey: ["review-queue"] });
      queryClient.invalidateQueries({ queryKey: ["evidence-item", updated.id] });
      queryClient.invalidateQueries({ queryKey: ["evidence-history", updated.id] });
    },
    onError: (error: Error & { code?: string }) => {
      if (error.code === "stale_version") {
        // reload the table so the selects show what actually won the race
        queryClient.invalidateQueries({ queryKey: ["evidence", workspaceId] });
      }
      toast.error(error.message);
    },
  });

  const exportJson = async () => {
    const { data, error } = await api.GET("/api/workspaces/{workspace_id}/evidence/export", {
      params: {
        path: { workspace_id: workspaceId },
        query: { include_history: includeHistory },
      },
    });
    if (!data) {
      toast.error(errorMessage(error, "Export failed"));
      return;
    }
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = window.document.createElement("a");
    link.href = url;
    link.download = "evidence-map.json";
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Evidence Map</h2>
          <p className="text-sm text-muted-foreground">
            Requirements extracted from your documents — every entry is backed by a
            quote verified against the source text.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={includeHistory}
              onChange={(event) => setIncludeHistory(event.target.checked)}
              className="size-3.5 accent-primary"
            />
            Include review history
          </label>
          <Button
            variant="outline"
            size="sm"
            onClick={exportJson}
            disabled={!items || items.length === 0}
          >
            <Download className="size-3.5" />
            JSON
          </Button>
          {/* anchors cannot be disabled, so the empty state gets a real disabled button */}
          {items && items.length > 0 ? (
            <Button
              variant="outline"
              size="sm"
              nativeButton={false}
              render={
                <a
                  href={`${API_BASE_URL}/api/workspaces/${workspaceId}/evidence/export.md?include_history=${includeHistory}`}
                />
              }
            >
              <Download className="size-3.5" />
              Markdown
            </Button>
          ) : (
            <Button variant="outline" size="sm" disabled>
              <Download className="size-3.5" />
              Markdown
            </Button>
          )}
        </div>
      </div>

      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (documentId) extract.mutate(documentId);
        }}
      >
        <NativeSelect
          value={documentId}
          onChange={(event) => setDocumentId(event.target.value)}
          aria-label="Document to extract from"
          className="max-w-64"
          disabled={generationOff}
        >
          <option value="">Select a document…</option>
          {readyDocuments.map((document) => (
            <option key={document.id} value={document.id}>
              {document.name}
            </option>
          ))}
        </NativeSelect>
        <Button type="submit" size="sm" disabled={!documentId || extract.isPending || generationOff}>
          {extract.isPending ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <ScanSearch className="size-4" />
          )}
          Extract requirements
        </Button>
        <p className="text-xs text-muted-foreground">
          {generationOff
            ? "Extraction requires a model API key on the server; reviewing existing evidence stays available."
            : "Re-extracting replaces unreviewed items; reviewed items are archived with their history intact."}
        </p>
      </form>

      {isPending ? (
        <div className="space-y-2">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
        </div>
      ) : isError ? (
        <EmptyState
          variant="error"
          title="Could not load the Evidence Map"
          description="Check that the API is reachable, then reload."
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={ScanSearch}
          title="No evidence yet"
          description={
            generationOff
              ? "Extraction needs a model API key on the server. Once configured, pick a processed document above to build the map."
              : "Pick a processed document above and extract its requirements — every entry is backed by a quote verified against the source text."
          }
        />
      ) : (
        <div className="overflow-x-auto rounded-xl border bg-card shadow-2xs">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="min-w-72">Requirement</TableHead>
                <TableHead>Evidence</TableHead>
                <TableHead className="w-36">Status</TableHead>
                <TableHead className="w-28">Risk</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="whitespace-normal align-top">
                    <p className="text-sm">{item.requirement_text}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{item.document_name}</p>
                  </TableCell>
                  <TableCell className="align-top">
                    <ul className="space-y-1">
                      {item.citations.map((citation) => (
                        <li key={citation.id}>
                          <button
                            type="button"
                            onClick={() =>
                              openEvidence({
                                documentId: item.document_id,
                                documentName: item.document_name,
                                page: citation.page_start,
                                quote: citation.quote,
                                clauseId: citation.clause_id,
                              })
                            }
                            className="inline-flex items-center gap-1.5 rounded border bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground transition-colors hover:border-info hover:text-foreground"
                            aria-label={`Verify evidence on ${item.document_name}, page ${citation.page_start}`}
                          >
                            <FileSearch className="size-3" />
                            {citation.clause_id ?? `p. ${citation.page_start}`}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </TableCell>
                  <TableCell className="align-top">
                    <NativeSelect
                      value={item.status}
                      onChange={(event) =>
                        update.mutate({
                          itemId: item.id,
                          version: item.version,
                          patch: { status: event.target.value as EvidenceStatus },
                        })
                      }
                      aria-label="Review status"
                      className="w-full px-2 text-xs"
                    >
                      {STATUS_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </NativeSelect>
                  </TableCell>
                  <TableCell className="align-top">
                    <NativeSelect
                      value={item.risk}
                      onChange={(event) =>
                        update.mutate({
                          itemId: item.id,
                          version: item.version,
                          patch: { risk: event.target.value as EvidenceRisk },
                        })
                      }
                      aria-label="Risk rating"
                      className={cn("w-full px-2 text-xs", RISK_CLASSES[item.risk])}
                    >
                      {RISK_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </NativeSelect>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {items && items.length > 0 && (
        <p className="text-xs text-muted-foreground">
          <span className="tabular-nums">
            {items.length} requirement{items.length === 1 ? "" : "s"}
          </span>
          <Badge variant="success" className="ml-2">
            all citations quote-verified
          </Badge>
        </p>
      )}
    </section>
  );
}
