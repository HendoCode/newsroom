import { AppHub } from "@/components/hub/app-hub";
import { HubShell } from "@/components/hub/hub-shell";
import { requireUser } from "@/lib/session";

/**
 * The post-login landing destination: the app hub. Middleware gates every non-signin route
 * already; `requireUser()` yields the typed signed-in user and redirects to /signin as
 * defense-in-depth, same convention as every other protected page. `lib/auth-actions.ts`'s
 * sign-in server action already defaults `redirectTo` to `/` when there's no deep-link
 * `callbackUrl`, so moving this root route to the hub (and the old root to `/newsroom`,
 * see `app/newsroom/page.tsx`) is what actually wires "land on the hub after login" —
 * no further redirect-callback change was needed.
 */
export default async function Hub() {
  const user = await requireUser();

  return (
    <HubShell user={user}>
      <section className="flex flex-col gap-6">
        <div>
          <h1 className="font-serif text-3xl font-semibold">Apps</h1>
          <p className="max-w-2xl text-sm text-muted-foreground">
            Pick an app to dive into. More apps will land here as the platform grows.
          </p>
        </div>
        <AppHub />
      </section>
    </HubShell>
  );
}
