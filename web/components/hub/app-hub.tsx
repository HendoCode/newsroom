import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { HUB_APPS, type HubApp } from "@/lib/hub/apps";

/**
 * The post-login app hub grid. Renders `HUB_APPS` (`lib/hub/apps.ts`) as cards — Content Machine
 * is the only enabled entry today, but the grid itself has no per-app knowledge, so a future
 * second app is a data addition there, not a change here. A disabled `enabled: false` entry
 * renders as a non-interactive card rather than a link; the trailing "more apps coming" tile is a
 * static, clearly-non-functional affordance, not a placeholder app.
 */
export function AppHub() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {HUB_APPS.map((app) => (
        <AppCard key={app.id} app={app} />
      ))}
      <ComingSoonCard />
    </div>
  );
}

function AppCard({ app }: { app: HubApp }) {
  const Icon = app.icon;
  return (
    <Card className="flex flex-col">
      <CardHeader>
        <span className="flex h-10 w-10 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <Icon className="h-5 w-5" aria-hidden />
        </span>
        <CardTitle className="mt-3 text-xl">{app.name}</CardTitle>
        <CardDescription>{app.blurb}</CardDescription>
      </CardHeader>
      <CardContent className="mt-auto pt-0">
        {app.enabled ? (
          <Button asChild>
            <Link href={app.href}>
              Open {app.name}
              <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
          </Button>
        ) : (
          <Button disabled title="Not available yet">
            Coming soon
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

function ComingSoonCard() {
  return (
    <div
      aria-hidden
      className="flex flex-col items-start justify-center gap-1 rounded-lg border border-dashed bg-muted/30 p-6 text-muted-foreground"
    >
      <span className="text-sm font-medium">More apps coming soon</span>
      <span className="text-xs">This platform will grow — new apps will show up here.</span>
    </div>
  );
}
