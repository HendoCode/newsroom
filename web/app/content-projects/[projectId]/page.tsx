import { AppShell } from "@/components/shell/app-shell";
import { requireUser } from "@/lib/session";

import type { ProjectWorkspaceView } from "@/lib/content-workflow/types";

import { PieceStudio } from "./piece-studio";

export default async function ContentProjectStudio({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const user = await requireUser();
  const { projectId } = await params;

  let view: ProjectWorkspaceView | null = null;
  let fetchError: string | null = null;
  try {
    const base = process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";
    const res = await fetch(`${base}/api/content-workflow/${projectId}/inspect`, {
      cache: "no-store",
    });
    if (!res.ok) {
      fetchError = "Couldn't load this project right now.";
    } else {
      view = (await res.json()) as ProjectWorkspaceView;
    }
  } catch {
    fetchError = "Couldn't load this project right now.";
  }

  return (
    <AppShell user={user} active="projects">
      <PieceStudio projectId={projectId} initialView={view} fetchError={fetchError} email={user.email} />
    </AppShell>
  );
}
