import { WorkspaceDetail } from "@/components/workspaces/workspace-detail";

export default async function WorkspacePage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const { id } = await params;
  const { tab, q } = await searchParams;
  return (
    <WorkspaceDetail
      workspaceId={id}
      initialTab={typeof tab === "string" ? tab : undefined}
      initialQuestion={typeof q === "string" ? q : undefined}
    />
  );
}
