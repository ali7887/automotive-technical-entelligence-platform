import { Columns2, FileJson, MessageSquareText, Network } from "lucide-react";

import { DashboardView } from "@/components/dashboard/dashboard-view";
import { CreateWorkspaceDialog } from "@/components/workspaces/workspace-dialogs";

/** Informational capability showcase; static by design — each card describes a
 *  shipped feature (Ask AI, compare, extraction, Evidence Map), no fetching. */
const CAPABILITIES = [
  {
    icon: MessageSquareText,
    title: "Ask AI",
    description: "Ask engineering questions with verified, page-level citations.",
  },
  {
    icon: Columns2,
    title: "Compare Regulations",
    description: "Compare standards or versions side by side for faster review.",
  },
  {
    icon: FileJson,
    title: "Extract Requirements",
    description: "Automatically extract structured requirements from uploaded PDFs.",
  },
  {
    icon: Network,
    title: "Evidence Map",
    description: "Trace every answer back to its original source.",
  },
] as const;

export default function HomePage() {
  return (
    <div className="space-y-10">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Automotive Technical Intelligence
          </p>
          <h1 className="text-4xl font-semibold tracking-tight">Dashboard</h1>
          <p className="mt-2 max-w-2xl text-base leading-relaxed text-muted-foreground">
            Search, analyze and compare automotive regulations with AI-powered verified
            citations.
          </p>
        </div>
        <CreateWorkspaceDialog />
      </div>
      <section aria-label="Platform capabilities" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {CAPABILITIES.map(({ icon: Icon, title, description }) => (
          <div
            key={title}
            className="rounded-xl border bg-card p-4 shadow-2xs transition-colors hover:border-foreground/20"
          >
            <Icon className="size-4 text-muted-foreground" aria-hidden />
            <p className="mt-2.5 text-sm font-medium">{title}</p>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{description}</p>
          </div>
        ))}
      </section>
      <DashboardView />
    </div>
  );
}
