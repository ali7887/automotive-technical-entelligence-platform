"use client";

import { Activity, FileText, Folder, Layers, Sparkles } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { WorkspaceGrid } from "@/components/workspaces/workspace-list";
import {
  useWorkspaceOverviews,
  type DashboardTotals,
} from "@/components/workspaces/use-workspace-overviews";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import type { Workspace } from "@/lib/api/types";
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
        <Skeleton className="mt-2 h-8 w-16" />
      ) : (
        <p
          className={cn("mt-1.5 text-2xl font-semibold tracking-tight tabular-nums", {
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

function queueStat(totals: DashboardTotals) {
  const value = String(totals.processing);
  if (totals.failed > 0) {
    return { value, hint: `${totals.failed} failed — needs attention`, tone: "danger" as const };
  }
  return {
    value,
    hint: "documents pending processing",
    tone: totals.processing > 0 ? ("warning" as const) : ("neutral" as const),
  };
}

const SUGGESTED_PROMPTS = [
  "FMVSS lighting requirements",
  "ISO 26262 safety integrity levels",
  "Euro 7 vs Euro 6d emission limits",
];

/** Global ask bar: questions run inside a workspace's Ask AI tab, so this
 *  routes there (carrying the question) rather than calling the API itself. */
function AskBar({ workspaces }: { workspaces: Workspace[] }) {
  const router = useRouter();
  const [question, setQuestion] = useState("");

  const onSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const submitted = question.trim();
    if (!submitted) return;
    if (workspaces.length === 0) {
      toast.info("Create a workspace and upload documents first — answers cite your sources.");
      return;
    }
    if (workspaces.length === 1) {
      router.push(`/workspaces/${workspaces[0].id}?tab=ask&q=${encodeURIComponent(submitted)}`);
      return;
    }
    toast.info(
      "Answers are grounded in one workspace's documents — choose a workspace below, or use Ask on its card.",
    );
  };

  return (
    <section className="space-y-3">
      <form onSubmit={onSubmit} className="flex gap-2">
        <div className="relative h-14 flex-1 rounded-lg border border-input bg-transparent shadow-sm transition-all hover:shadow focus-within:border-primary/40 focus-within:ring-2 focus-within:ring-primary/20">
          <Sparkles className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-muted-foreground/60" />
          <Input
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask anything across all active automotive workspaces..."
            maxLength={500}
            aria-label="Ask a question about your documents"
            className="h-14 border-transparent bg-transparent pl-11 pr-5 text-base shadow-none focus-visible:border-transparent focus-visible:ring-0 md:text-base"
          />
        </div>
        <Button
          type="submit"
          disabled={!question.trim()}
          className="h-14 px-6 text-base transition-all duration-150 disabled:pointer-events-auto disabled:cursor-not-allowed disabled:opacity-40"
        >
          Ask
        </Button>
      </form>
      <div className="flex flex-wrap items-center gap-1.5">
        {SUGGESTED_PROMPTS.map((prompt) => (
          <Button
            key={prompt}
            type="button"
            variant="outline"
            size="xs"
            className="rounded-full font-normal text-muted-foreground transition-transform hover:scale-[1.02]"
            onClick={() => setQuestion(prompt)}
          >
            {prompt}
          </Button>
        ))}
      </div>
    </section>
  );
}

/** Dashboard: system-wide rollup on top, workspace grid below. */
export function DashboardView() {
  const { workspaces, overviews, totals, isPending, isError, refetch } = useWorkspaceOverviews();
  const queue = totals ? queueStat(totals) : null;
  const populated = [...overviews.values()].filter((o) => o.documentCount > 0).length;

  return (
    <div className="space-y-8">
      <AskBar workspaces={workspaces} />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Active Workspaces"
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
          label="Knowledge Pages"
          value={totals ? totals.pages.toLocaleString() : null}
          hint={totals ? "verified regulatory clauses" : null}
          icon={Layers}
        />
        <StatCard
          label="Queue"
          value={queue ? queue.value : null}
          hint={queue?.hint}
          icon={Activity}
          tone={queue?.tone}
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
