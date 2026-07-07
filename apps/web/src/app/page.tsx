import { WorkspaceList } from "@/components/workspaces/workspace-list";
import { CreateWorkspaceDialog } from "@/components/workspaces/workspace-dialogs";

export default function HomePage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Workspaces</h1>
          <p className="text-sm text-muted-foreground">
            Compliance and engineering document collections
          </p>
        </div>
        <CreateWorkspaceDialog />
      </div>
      <WorkspaceList />
    </div>
  );
}
