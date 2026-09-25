import { LayoutGrid } from "lucide-react";

import { UserMenu } from "@/components/auth/user-menu";
import { ThemeToggle } from "@/components/theme-toggle";
import type { AppUser } from "@/lib/session";

/**
 * The platform-level frame for the post-login app hub (`app/page.tsx`) — deliberately its OWN
 * small header rather than a reuse of `AppShell`: `AppShell`'s nav is Content Machine's internal
 * sections (Dashboard/Spikes/Sources/Voice kits), which don't belong one level up on the app
 * picker itself. Reuses the same token-driven header chrome and the shared `ThemeToggle`/
 * `UserMenu` controls so it still feels like one system.
 */
export function HubShell({
  user,
  children,
}: {
  user: AppUser;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-3">
          <div className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <LayoutGrid className="h-5 w-5" aria-hidden />
            </span>
            <span className="flex flex-col leading-tight">
              <span className="font-serif text-lg font-semibold">App hub</span>
              <span className="text-xs text-muted-foreground">Hendo Code</span>
            </span>
          </div>
          <div className="flex items-center gap-4">
            <ThemeToggle />
            <UserMenu user={user} />
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">{children}</main>
    </div>
  );
}
