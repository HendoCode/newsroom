import Link from "next/link";

import { AppShell } from "@/components/shell/app-shell";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchContentWorkflowDesk } from "@/lib/agents-client";
import type { ContentProject } from "@/lib/content-workflow/types";
import { requireUser } from "@/lib/session";

export const dynamic = "force-dynamic";

/** All current Content Workflow projects assigned to the signed-in operator. */
export default async function ContentProjectsPage() {
  const user = await requireUser();
  let projects: ContentProject[] = [];
  let fetchError: string | null = null;

  try {
    projects = (await fetchContentWorkflowDesk(user.email)).active_work;
  } catch (error) {
    fetchError = error instanceof Error ? error.message : "Could not load projects";
  }

  return (
    <AppShell user={user} active="projects">
      <section className="space-y-6">
        <div>
          <h1 className="font-serif text-3xl font-semibold">Content Projects</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            In-progress projects assigned to you, with their current evidence and production work.
          </p>
        </div>

        {fetchError ? (
          <Card>
            <CardContent className="py-6 text-destructive">{fetchError}</CardContent>
          </Card>
        ) : projects.length === 0 ? (
          <Card>
            <CardContent className="py-6 text-muted-foreground">
              No in-progress projects assigned to you yet.
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {projects.map((project) => (
              <Link
                key={project.id}
                href={`/content-projects/${project.id}`}
                className="rounded-lg focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
              >
                <Card className="h-full transition-colors hover:bg-accent">
                  <CardHeader>
                    <div className="flex items-start justify-between gap-3">
                      <CardTitle className="text-xl">{project.title}</CardTitle>
                      <Badge variant="secondary">in progress</Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm text-muted-foreground">
                    <p>{project.purpose_brief.proposition}</p>
                    <p>
                      {project.purpose_brief.audience} · {project.purpose_brief.angle}
                    </p>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </section>
    </AppShell>
  );
}
