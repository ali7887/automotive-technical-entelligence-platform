"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  CheckCircle2,
  FileSearch,
  History,
  Loader2,
  MessageSquare,
  Play,
  Undo2,
  X,
  XCircle,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  REVIEW_ACTION_LABELS,
  REVIEW_STATUS_CLASSES,
  REVIEW_STATUS_LABELS,
  RISK_LABELS,
  RISK_TEXT_CLASSES,
} from "@/components/review/review-labels";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api/client";
import type {
  EvidenceRisk,
  ReviewEvent,
  SubmittableReviewAction,
} from "@/lib/api/types";
import { errorMessage } from "@/lib/api/types";
import { loadReviewerName, reviewerOrAnonymous, saveReviewerName } from "@/lib/reviewer";
import { useEvidenceViewer } from "@/lib/store";
import { cn } from "@/lib/utils";

function formatTimestamp(value: string): string {
  return new Date(value).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function TimelineEvent({ event }: { event: ReviewEvent }) {
  const statusChanged = event.previous_status !== event.next_status;
  const riskChanged = event.previous_risk !== event.next_risk;
  return (
    <li className="group relative pb-4 pl-6 last:pb-0">
      <span className="absolute top-1.5 left-0 size-2 rounded-full bg-border" aria-hidden />
      <span className="absolute top-4 bottom-0 left-0.75 w-px bg-border group-last:hidden" aria-hidden />
      <p className="text-sm">
        <span className="font-medium">{REVIEW_ACTION_LABELS[event.action]}</span>
        <span className="text-muted-foreground"> — {event.actor_name}</span>
        {event.actor_type === "SYSTEM" && (
          <Badge variant="outline" className="ml-1.5 align-middle">
            system
          </Badge>
        )}
      </p>
      <p className="text-xs text-muted-foreground">{formatTimestamp(event.created_at)}</p>
      {statusChanged && (
        <p className="mt-0.5 text-xs text-muted-foreground">
          {REVIEW_STATUS_LABELS[event.previous_status]} →{" "}
          <span className={REVIEW_STATUS_CLASSES[event.next_status]}>
            {REVIEW_STATUS_LABELS[event.next_status]}
          </span>
        </p>
      )}
      {riskChanged && (
        <p className="mt-0.5 text-xs text-muted-foreground">
          Risk: {RISK_LABELS[event.previous_risk]} →{" "}
          <span className={RISK_TEXT_CLASSES[event.next_risk]}>
            {RISK_LABELS[event.next_risk]}
          </span>
        </p>
      )}
      {event.action === "SET_STATUS" && event.extra && (
        <p className="mt-0.5 text-xs text-muted-foreground">
          Compliance: {String(event.extra.previous)} → {String(event.extra.next)}
        </p>
      )}
      {event.comment && (
        <blockquote className="mt-1 rounded border-l-2 bg-muted/50 px-2 py-1 text-xs">
          {event.comment}
        </blockquote>
      )}
    </li>
  );
}

/** Slide-over drawer with item detail, review actions, and the audit timeline. */
export function ReviewDetailDrawer({
  itemId,
  workspaceId,
  onClose,
}: {
  itemId: string;
  workspaceId: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const openEvidence = useEvidenceViewer((state) => state.openEvidence);
  const viewerOpen = useEvidenceViewer((state) => state.target !== null);

  const [reviewer, setReviewer] = useState(loadReviewerName);
  const [comment, setComment] = useState("");
  // null = "not touched yet"; the select falls back to the item's current risk
  const [riskDraft, setRiskDraft] = useState<EvidenceRisk | null>(null);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      // the PDF viewer stacks above this drawer and owns Escape while open
      if (event.key === "Escape" && !useEvidenceViewer.getState().target) onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const { data: item, isPending: itemPending } = useQuery({
    queryKey: ["evidence-item", itemId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/evidence/{item_id}", {
        params: { path: { item_id: itemId } },
      });
      if (!data) throw new Error(errorMessage(error, "Failed to load evidence item"));
      return data;
    },
  });

  const { data: history } = useQuery({
    queryKey: ["evidence-history", itemId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/evidence/{item_id}/history", {
        params: { path: { item_id: itemId } },
      });
      if (!data) throw new Error(errorMessage(error, "Failed to load review history"));
      return data;
    },
  });

  const review = useMutation({
    mutationFn: async (input: {
      action: SubmittableReviewAction;
      comment?: string;
      risk?: EvidenceRisk;
    }) => {
      const actorName = reviewerOrAnonymous(reviewer);
      saveReviewerName(reviewer);
      const { data, error } = await api.POST("/api/evidence/{item_id}/review", {
        params: { path: { item_id: itemId } },
        body: {
          action: input.action,
          actor_name: actorName,
          actor_type: "HUMAN",
          comment: input.comment,
          risk: input.risk,
          // optimistic lock: act on the version this drawer is showing
          expected_version: item?.version,
        },
      });
      if (!data) {
        const failure = new Error(errorMessage(error, "Review action failed")) as Error & {
          code?: string;
        };
        failure.code = (error as { code?: string } | undefined)?.code;
        throw failure;
      }
      return data;
    },
    onSuccess: (result) => {
      setComment("");
      setRiskDraft(null);
      queryClient.invalidateQueries({ queryKey: ["evidence-item", itemId] });
      queryClient.invalidateQueries({ queryKey: ["evidence-history", itemId] });
      queryClient.invalidateQueries({ queryKey: ["review-queue"] });
      queryClient.invalidateQueries({ queryKey: ["evidence", workspaceId] });
      toast.success(REVIEW_ACTION_LABELS[result.event.action]);
    },
    onError: (error: Error & { code?: string }) => {
      if (error.code === "stale_version") {
        // someone else changed the item; refetch so the drawer shows the truth
        queryClient.invalidateQueries({ queryKey: ["evidence-item", itemId] });
        queryClient.invalidateQueries({ queryKey: ["evidence-history", itemId] });
        queryClient.invalidateQueries({ queryKey: ["review-queue"] });
      }
      toast.error(error.message);
    },
  });

  const act = (action: SubmittableReviewAction, extra?: { comment?: string; risk?: EvidenceRisk }) =>
    review.mutate({ action, ...extra });

  const trimmedComment = comment.trim();
  const status = item?.review_status;
  const archived = Boolean(item?.archived_at);
  const busy = review.isPending;

  return (
    <div className={cn("fixed inset-0 z-40", viewerOpen && "invisible")}>
      <button
        type="button"
        aria-label="Close review details"
        onClick={onClose}
        className="absolute inset-0 bg-black/50"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Evidence review details"
        className="absolute inset-y-0 right-0 flex w-full max-w-xl flex-col border-l bg-background shadow-xl"
      >
        <header className="flex items-start gap-2 border-b px-4 py-3">
          <div className="min-w-0 flex-1">
            {itemPending || !item ? (
              <Skeleton className="h-6 w-64" />
            ) : (
              <>
                <p className="text-sm font-medium">{item.requirement_text}</p>
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                  <Badge variant="outline" className={REVIEW_STATUS_CLASSES[item.review_status]}>
                    {REVIEW_STATUS_LABELS[item.review_status]}
                  </Badge>
                  <Badge variant="outline" className={RISK_TEXT_CLASSES[item.risk]}>
                    {RISK_LABELS[item.risk]} risk
                  </Badge>
                  {archived && (
                    <Badge variant="outline">
                      <Archive className="size-3" /> archived
                    </Badge>
                  )}
                  <span className="text-xs text-muted-foreground">{item.document_name}</span>
                </div>
              </>
            )}
          </div>
          <Button variant="ghost" size="icon" aria-label="Close" onClick={onClose}>
            <X className="size-4" />
          </Button>
        </header>

        <div className="flex-1 space-y-5 overflow-y-auto px-4 py-4">
          {item && (
            <section>
              <h3 className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
                Verified evidence
              </h3>
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
                      className="flex w-full items-start gap-2 rounded border bg-muted/50 px-2 py-1.5 text-left text-xs transition-colors hover:border-primary"
                      aria-label={`Open evidence on page ${citation.page_start}`}
                    >
                      <FileSearch className="mt-0.5 size-3 shrink-0 text-muted-foreground" />
                      <span>
                        <span className="font-medium">
                          {citation.clause_id ?? `p. ${citation.page_start}`}
                        </span>{" "}
                        <span className="text-muted-foreground">“{citation.quote}”</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {archived ? (
            <p className="rounded-md border border-dashed px-3 py-2 text-sm text-muted-foreground">
              This item was archived by a re-extraction and is read-only; its history below is
              preserved.
            </p>
          ) : (
            item && (
              <section className="space-y-3">
                <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                  Review actions
                </h3>
                <div className="flex items-center gap-2">
                  <label htmlFor="reviewer-name" className="text-xs text-muted-foreground">
                    Reviewer
                  </label>
                  <Input
                    id="reviewer-name"
                    value={reviewer}
                    onChange={(event) => setReviewer(event.target.value)}
                    placeholder="anonymous"
                    maxLength={120}
                    className="h-8 max-w-48 text-xs"
                  />
                </div>
                <div className="flex flex-wrap gap-2">
                  {status !== "IN_REVIEW" && (
                    <Button size="sm" disabled={busy} onClick={() => act("START_REVIEW")}>
                      <Play className="size-3.5" />
                      {status === "NEW" ? "Start review" : "Reopen review"}
                    </Button>
                  )}
                  {status === "IN_REVIEW" && (
                    <>
                      <Button size="sm" disabled={busy} onClick={() => act("APPROVE")}>
                        <CheckCircle2 className="size-3.5" />
                        Approve
                      </Button>
                      <Button
                        size="sm"
                        variant="destructive"
                        disabled={busy || !trimmedComment}
                        onClick={() => act("REJECT", { comment: trimmedComment })}
                      >
                        <XCircle className="size-3.5" />
                        Reject
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={busy || !trimmedComment}
                        onClick={() => act("REQUEST_REVISION", { comment: trimmedComment })}
                      >
                        <Undo2 className="size-3.5" />
                        Request revision
                      </Button>
                    </>
                  )}
                </div>
                <div className="space-y-1.5">
                  <textarea
                    value={comment}
                    onChange={(event) => setComment(event.target.value)}
                    rows={2}
                    placeholder={
                      status === "IN_REVIEW"
                        ? "Comment (required to reject or request revision)…"
                        : "Add a comment…"
                    }
                    aria-label="Review comment"
                    className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy || !trimmedComment}
                    onClick={() => act("COMMENT", { comment: trimmedComment })}
                  >
                    <MessageSquare className="size-3.5" />
                    Add comment
                  </Button>
                </div>
                <div className="flex items-center gap-2">
                  <label htmlFor="review-risk" className="text-xs text-muted-foreground">
                    Risk
                  </label>
                  <select
                    id="review-risk"
                    value={riskDraft ?? item.risk}
                    onChange={(event) => setRiskDraft(event.target.value as EvidenceRisk)}
                    className="h-8 rounded-md border border-input bg-transparent px-2 text-xs shadow-xs focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                  >
                    {(Object.keys(RISK_LABELS) as EvidenceRisk[]).map((value) => (
                      <option key={value} value={value}>
                        {RISK_LABELS[value]}
                      </option>
                    ))}
                  </select>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy || riskDraft === null || riskDraft === item.risk}
                    onClick={() => riskDraft && act("SET_RISK", { risk: riskDraft })}
                  >
                    Apply risk
                  </Button>
                  {busy && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
                </div>
              </section>
            )
          )}

          <section>
            <h3 className="mb-2 flex items-center gap-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">
              <History className="size-3.5" />
              History
            </h3>
            {!history ? (
              <Skeleton className="h-12 w-full" />
            ) : history.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No review activity yet — every action is recorded here permanently.
              </p>
            ) : (
              <ol className="group/event">
                {[...history].reverse().map((event) => (
                  <TimelineEvent key={event.id} event={event} />
                ))}
              </ol>
            )}
          </section>
        </div>
      </aside>
    </div>
  );
}
