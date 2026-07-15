import { DashboardView } from "@/components/dashboard/dashboard-view";
import { CreateWorkspaceDialog } from "@/components/workspaces/workspace-dialogs";

export default function HomePage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Compliance and engineering document collections
          </p>
        </div>
        <CreateWorkspaceDialog />
      </div>
      <DashboardView />
    </div>
  );
}
