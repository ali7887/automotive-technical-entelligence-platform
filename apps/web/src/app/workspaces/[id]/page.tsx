import { WorkspaceDetail } from "@/components/workspaces/workspace-detail";

export default async function WorkspacePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <WorkspaceDetail workspaceId={id} />;
}
