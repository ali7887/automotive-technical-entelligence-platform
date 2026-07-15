"use client";

import { Activity, FileText, Folder, Layers } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { WorkspaceGrid } from "@/components/workspaces/workspace-list";
import {
  useWorkspaceOverviews,
  type DashboardTotals,
} from "@/components/workspaces/use-workspace-overviews";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  tone = "neutral",
}: {
  label: string;
  value: string | null;
  hint?: string | null;
  icon: LucideIcon;
  tone?: "neutral" | "success" | "warning" | "danger";
}) {
  return (
    <div className="rounded-xl border bg-card p-4 shadow-2xs">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        <Icon className="size-3.5 text-muted-foreground/60" />
      </div>
      {value === null ? (
        <Skeleton className="mt-2 h-7 w-16" />
      ) : (
        <p
          className={cn("mt-1.5 text-xl font-semibold tracking-tight tabular-nums", {
            "text-success-strong": tone === "success",
            "text-warning-strong": tone === "warning",
            "text-destructive-strong": tone === "danger",
          })}
        >
          {value}
        </p>
      )}
      {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

function processingStat(totals: DashboardTotals) {
  if (totals.failed > 0) {
    return {
      value: `${totals.failed} failed`,
      hint: totals.processing > 0 ? `${totals.processing} still processing` : "needs attention",
      tone: "danger" as const,
    };
  }
  if (totals.processing > 0) {
    return { value: `${totals.processing} processing`, hint: "documents in pipeline", tone: "warning" as const };
  }
  if (totals.documents === 0) {
    return { value: "Idle", hint: "no documents uploaded yet", tone: "neutral" as const };
  }
  return { value: "All ready", hint: "no documents in pipeline", tone: "success" as const };
}

/** Dashboard: system-wide rollup on top, workspace grid below. */
export function DashboardView() {
  const { workspaces, overviews, totals, isPending, isError, refetch } = useWorkspaceOverviews();
  const processing = totals ? processingStat(totals) : null;
  const populated = [...overviews.values()].filter((o) => o.documentCount > 0).length;

  return (
    <div className="space-y-8">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Workspaces"
          value={totals ? String(totals.workspaces) : null}
          hint={
            totals
              ? totals.workspaces === 0
                ? "create one to get started"
                : `${populated} with documents`
              : null
          }
          icon={Folder}
        />
        <StatCard
          label="Documents"
          value={totals ? String(totals.documents) : null}
          hint={totals ? `${totals.ready} ready for analysis` : null}
          icon={FileText}
        />
        <StatCard
          label="Pages indexed"
          value={totals ? totals.pages.toLocaleString() : null}
          hint="clause-aware chunked sources"
          icon={Layers}
        />
        <StatCard
          label="Processing"
          value={processing ? processing.value : null}
          hint={processing?.hint}
          icon={Activity}
          tone={processing?.tone}
        />
      </div>

      <section className="space-y-4">
        <h2 className="text-sm font-medium text-muted-foreground">Workspaces</h2>
        <WorkspaceGrid
          workspaces={workspaces}
          overviews={overviews}
          isPending={isPending}
          isError={isError}
          onRetry={() => refetch()}
        />
      </section>
    </div>
  );
}
