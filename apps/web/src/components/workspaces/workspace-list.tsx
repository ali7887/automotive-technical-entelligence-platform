"use client";

import { ChevronRight, FolderOpen, MoreHorizontal } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import {
  CreateWorkspaceDialog,
  DeleteWorkspaceDialog,
  RenameWorkspaceDialog,
} from "@/components/workspaces/workspace-dialogs";
import type { WorkspaceOverview } from "@/components/workspaces/use-workspace-overviews";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate } from "@/lib/format";
import type { Workspace } from "@/lib/api/types";

function WorkspaceStateBadge({ overview }: { overview: WorkspaceOverview }) {
  if (overview.failedCount > 0) {
    return (
      <Badge variant="destructive">
        {overview.failedCount} failed
      </Badge>
    );
  }
  if (overview.processingCount > 0) {
    return <Badge variant="warning">Processing {overview.processingCount}</Badge>;
  }
  if (overview.readyCount > 0) {
    return <Badge variant="success">Ready</Badge>;
  }
  return <Badge variant="neutral">Empty</Badge>;
}

function WorkspaceCard({
  workspace,
  overview,
}: {
  workspace: Workspace;
  overview?: WorkspaceOverview;
}) {
  const [renaming, setRenaming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  return (
    <Card className="group relative gap-3 transition-all hover:border-foreground/25 hover:shadow-xs has-[a:focus-visible]:border-ring has-[a:focus-visible]:ring-3 has-[a:focus-visible]:ring-ring/50">
      {/* stretched link: the whole card opens the workspace */}
      <Link
        href={`/workspaces/${workspace.id}`}
        className="absolute inset-0 z-0 rounded-xl outline-none"
        aria-label={`Open workspace ${workspace.name}`}
      />
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="min-w-0 flex-1 truncate">{workspace.name}</CardTitle>
          <div className="relative z-10 -mt-1 flex shrink-0 items-center">
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button variant="ghost" size="icon-sm" aria-label="Workspace actions">
                    <MoreHorizontal className="size-4" />
                  </Button>
                }
              />
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => setRenaming(true)}>Rename</DropdownMenuItem>
                <DropdownMenuItem variant="destructive" onClick={() => setDeleting(true)}>
                  Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {overview ? (
            <WorkspaceStateBadge overview={overview} />
          ) : (
            <Skeleton className="h-5 w-16" />
          )}
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
          {overview ? (
            <>
              <span className="tabular-nums">
                {overview.documentCount} document{overview.documentCount === 1 ? "" : "s"}
                {overview.pageCount > 0 && <> · {overview.pageCount.toLocaleString()} pages</>}
              </span>
              <span className="flex items-center gap-1 tabular-nums">
                Updated {formatDate(overview.updatedAt)}
                <ChevronRight className="size-3.5 text-muted-foreground/50 transition-transform group-hover:translate-x-0.5 group-hover:text-muted-foreground" />
              </span>
            </>
          ) : (
            <Skeleton className="h-4 w-40" />
          )}
        </div>
      </CardContent>
      <RenameWorkspaceDialog workspace={workspace} open={renaming} onOpenChange={setRenaming} />
      <DeleteWorkspaceDialog workspace={workspace} open={deleting} onOpenChange={setDeleting} />
    </Card>
  );
}

export function WorkspaceGrid({
  workspaces,
  overviews,
  isPending,
  isError,
  onRetry,
}: {
  workspaces: Workspace[];
  overviews: Map<string, WorkspaceOverview>;
  isPending: boolean;
  isError: boolean;
  onRetry: () => void;
}) {
  if (isPending) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-32 rounded-xl" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <EmptyState
        variant="error"
        title="Could not load workspaces"
        description="Check that the API is running, then try again."
        action={
          <Button variant="outline" onClick={onRetry}>
            Retry
          </Button>
        }
      />
    );
  }

  if (workspaces.length === 0) {
    return (
      <EmptyState
        icon={FolderOpen}
        title="No workspaces yet"
        description="A workspace groups the documents for one regulation, standard, or project — e.g. ECE-R13 Rev 5 or ISO 26262 Part 6."
        action={<CreateWorkspaceDialog />}
      />
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {workspaces.map((workspace) => (
        <WorkspaceCard
          key={workspace.id}
          workspace={workspace}
          overview={overviews.get(workspace.id)}
        />
      ))}
    </div>
  );
}
