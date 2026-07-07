"use client";

import { useQuery } from "@tanstack/react-query";
import { MoreHorizontal } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import {
  DeleteWorkspaceDialog,
  RenameWorkspaceDialog,
} from "@/components/workspaces/workspace-dialogs";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api/client";
import type { Workspace } from "@/lib/api/types";

function WorkspaceCard({ workspace }: { workspace: Workspace }) {
  const [renaming, setRenaming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  return (
    <Card className="relative transition-colors hover:bg-accent/40">
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <Link href={`/workspaces/${workspace.id}`} className="min-w-0 flex-1">
            <CardTitle className="truncate">{workspace.name}</CardTitle>
            <CardDescription className="mt-1">
              Created {new Date(workspace.created_at).toLocaleDateString()}
            </CardDescription>
          </Link>
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <Button variant="ghost" size="icon" aria-label="Workspace actions">
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
      </CardHeader>
      <RenameWorkspaceDialog workspace={workspace} open={renaming} onOpenChange={setRenaming} />
      <DeleteWorkspaceDialog workspace={workspace} open={deleting} onOpenChange={setDeleting} />
    </Card>
  );
}

export function WorkspaceList() {
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["workspaces"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/workspaces");
      if (!data) throw new Error(String(error ?? "Failed to load workspaces"));
      return data;
    },
  });

  if (isPending) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-28 rounded-xl" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-xl border border-dashed p-10 text-center">
        <p className="font-medium">Could not load workspaces</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Check that the API is running, then try again.
        </p>
        <Button variant="outline" className="mt-4" onClick={() => refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="rounded-xl border border-dashed p-10 text-center">
        <p className="font-medium">No workspaces yet</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Create a workspace to start uploading regulations and standards.
        </p>
      </div>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {data.map((workspace) => (
        <WorkspaceCard key={workspace.id} workspace={workspace} />
      ))}
    </div>
  );
}
