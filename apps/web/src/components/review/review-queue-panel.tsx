"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, ClipboardCheck } from "lucide-react";
import { useState } from "react";

import { ReviewDetailDrawer } from "@/components/review/review-detail-drawer";
import {
  REVIEW_STATUS_CLASSES,
  REVIEW_STATUS_LABELS,
  RISK_LABELS,
  RISK_TEXT_CLASSES,
} from "@/components/review/review-labels";
import { Badge } from "@/components/ui/badge";
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
import type { EvidenceRisk, ReviewStatus } from "@/lib/api/types";
import { errorMessage } from "@/lib/api/types";
import { cn } from "@/lib/utils";

type QueueSort =
  | "updated_desc"
  | "updated_asc"
  | "created_desc"
  | "created_asc"
  | "risk_desc"
  | "risk_asc";

const SORT_OPTIONS: { value: QueueSort; label: string }[] = [
  { value: "updated_desc", label: "Recently updated" },
  { value: "updated_asc", label: "Least recently updated" },
  { value: "created_desc", label: "Newest" },
  { value: "created_asc", label: "Oldest" },
  { value: "risk_desc", label: "Highest risk" },
  { value: "risk_asc", label: "Lowest risk" },
];

const PAGE_SIZE = 20;

const filterSelectClass =
  "h-8 rounded-md border border-input bg-transparent px-2 text-xs shadow-xs focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50";

/** Review Queue: filterable, sortable list of evidence items awaiting human review. */
export function ReviewQueuePanel({ workspaceId }: { workspaceId: string }) {
  const [reviewStatus, setReviewStatus] = useState<ReviewStatus | "">("");
  const [risk, setRisk] = useState<EvidenceRisk | "">("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [sort, setSort] = useState<QueueSort>("updated_desc");
  const [offset, setOffset] = useState(0);
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);

  const filters = { reviewStatus, risk, includeArchived, sort, offset };
  const { data: page, isPending, isError } = useQuery({
    queryKey: ["review-queue", workspaceId, filters],
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/evidence/review-queue", {
        params: {
          query: {
            workspace_id: workspaceId,
            review_status: reviewStatus || null,
            risk: risk || null,
            include_archived: includeArchived,
            sort,
            limit: PAGE_SIZE,
            offset,
          },
        },
      });
      if (!data) throw new Error(errorMessage(error, "Failed to load review queue"));
      return data;
    },
  });

  const resetPage = () => setOffset(0);
  const total = page?.total ?? 0;
  const hasFilters = reviewStatus !== "" || risk !== "" || includeArchived;

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Review Queue</h2>
          <p className="text-sm text-muted-foreground">
            Human review of extracted evidence — every decision is recorded in a permanent
            audit trail.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={reviewStatus}
            onChange={(event) => {
              setReviewStatus(event.target.value as ReviewStatus | "");
              resetPage();
            }}
            aria-label="Filter by review status"
            className={filterSelectClass}
          >
            <option value="">All review states</option>
            {(Object.keys(REVIEW_STATUS_LABELS) as ReviewStatus[]).map((value) => (
              <option key={value} value={value}>
                {REVIEW_STATUS_LABELS[value]}
              </option>
            ))}
          </select>
          <select
            value={risk}
            onChange={(event) => {
              setRisk(event.target.value as EvidenceRisk | "");
              resetPage();
            }}
            aria-label="Filter by risk"
            className={filterSelectClass}
          >
            <option value="">All risks</option>
            {(Object.keys(RISK_LABELS) as EvidenceRisk[]).map((value) => (
              <option key={value} value={value}>
                {RISK_LABELS[value]}
              </option>
            ))}
          </select>
          <select
            value={sort}
            onChange={(event) => {
              setSort(event.target.value as QueueSort);
              resetPage();
            }}
            aria-label="Sort queue"
            className={filterSelectClass}
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={includeArchived}
              onChange={(event) => {
                setIncludeArchived(event.target.checked);
                resetPage();
              }}
              className="size-3.5 accent-primary"
            />
            Archived
          </label>
        </div>
      </div>

      {isPending ? (
        <div className="space-y-2">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
        </div>
      ) : isError ? (
        <div className="rounded-xl border border-destructive/50 p-6 text-center text-sm">
          <p className="font-medium">Could not load the review queue</p>
          <p className="mt-1 text-muted-foreground">Check that the API is reachable.</p>
        </div>
      ) : page.items.length === 0 ? (
        <div className="rounded-xl border border-dashed p-6 text-center">
          <p className="font-medium">
            {hasFilters ? "Nothing matches these filters" : "Queue is empty"}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {hasFilters
              ? "Relax the filters to see more items."
              : "Extract requirements in the Evidence Map to fill the review queue."}
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="min-w-72">Requirement</TableHead>
                <TableHead className="w-32">Review</TableHead>
                <TableHead className="w-24">Risk</TableHead>
                <TableHead className="w-20 text-right">Evidence</TableHead>
                <TableHead className="w-36">Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {page.items.map((item) => (
                <TableRow
                  key={item.id}
                  onClick={() => setSelectedItemId(item.id)}
                  className="cursor-pointer"
                  aria-label={`Review ${item.requirement_text}`}
                >
                  <TableCell className="whitespace-normal align-top">
                    <p className="line-clamp-2 text-sm">{item.requirement_text}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{item.document_name}</p>
                  </TableCell>
                  <TableCell className="align-top">
                    <Badge variant="outline" className={REVIEW_STATUS_CLASSES[item.review_status]}>
                      {REVIEW_STATUS_LABELS[item.review_status]}
                    </Badge>
                  </TableCell>
                  <TableCell className={cn("align-top text-xs", RISK_TEXT_CLASSES[item.risk])}>
                    {RISK_LABELS[item.risk]}
                  </TableCell>
                  <TableCell className="align-top text-right text-xs text-muted-foreground">
                    {item.citation_count}
                  </TableCell>
                  <TableCell className="align-top text-xs text-muted-foreground">
                    {new Date(item.updated_at).toLocaleString(undefined, {
                      dateStyle: "medium",
                      timeStyle: "short",
                    })}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {page && total > 0 && (
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <p className="flex items-center gap-2">
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
            <Badge variant="outline">
              <ClipboardCheck className="size-3" />
              append-only audit trail
            </Badge>
          </p>
          <div className="flex gap-1">
            <Button
              variant="outline"
              size="sm"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              <ChevronLeft className="size-3.5" />
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={offset + PAGE_SIZE >= total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next
              <ChevronRight className="size-3.5" />
            </Button>
          </div>
        </div>
      )}

      {selectedItemId && (
        <ReviewDetailDrawer
          itemId={selectedItemId}
          workspaceId={workspaceId}
          onClose={() => setSelectedItemId(null)}
        />
      )}
    </section>
  );
}
