import Link from "next/link";
import { LayoutGrid, Sparkles } from "lucide-react";

import { UserMenu } from "@/components/auth/user-menu";
import { ThemeToggle } from "@/components/theme-toggle";
import { Badge } from "@/components/ui/badge";
import type { AppUser } from "@/lib/session";
import { cn } from "@/lib/utils";

/**
 * The Newsroom app shell — the top-level frame every Newsroom screen mounts into
 * (behind the auth gate; `requireUser()` yields the signed-in user, middleware already protected
 * the route). It owns the brand bar, the light/dark toggle (wired to the skeleton's token theme
 * via `ThemeToggle`), the sign-in/out control (`UserMenu`), the app-section nav, and a small
 * app-hub link back to the platform-level app picker (`app/page.tsx`) now that Newsroom is
 * one app among (eventually) several rather than the root landing page itself.
 *
 * Only the Dashboard section is built in this ticket; the other sections are rendered as visible
 * SEAMS so the frame is complete and later tickets have an obvious mount point. Everything is
 * token-driven — no brand literal lives here (re-skin via `globals.css`).
 */

const NAV_SECTIONS = [
  { key: "dashboard", label: "Dashboard", href: "/content-machine", ready: true },
  { key: "library", label: "Library", href: "/content-machine#library", ready: true },
  { key: "new-idea", label: "New idea", href: "/pieces/new", ready: true },
  { key: "radar", label: "Radar", href: "/narrative", ready: true },
  { key: "spikes", label: "Spikes & Vault", href: "/spikes", ready: true },
  { key: "sources", label: "Sources", href: "/sources", ready: true },
  { key: "voices", label: "Voice kits", href: "/voice-kit", ready: true },
  { key: "projects", label: "Content projects", href: "/content-projects", ready: true },
] as const;

export function AppShell({
  user,
  active = "dashboard",
  children,
}: {
  user: AppUser;
  active?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-3">
          <div className="flex items-center gap-3">
            <Link
              href="/"
              aria-label="Back to app hub"
              title="App hub"
              className="flex h-9 w-9 items-center justify-center rounded-md border text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
            >
              <LayoutGrid className="h-4 w-4" aria-hidden />
            </Link>
            <Link href="/content-machine" className="flex items-center gap-2">
              <span className="flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
                <Sparkles className="h-5 w-5" aria-hidden />
              </span>
              <span className="flex flex-col leading-tight">
                <span className="font-serif text-lg font-semibold">Newsroom</span>
                <span className="text-xs text-muted-foreground">Hendo Code</span>
              </span>
            </Link>
          </div>
          <div className="flex items-center gap-4">
            <ThemeToggle />
            <UserMenu user={user} />
          </div>
        </div>

        <nav className="mx-auto flex max-w-6xl items-center gap-1 overflow-x-auto px-6" aria-label="Sections">
          {NAV_SECTIONS.map((s) =>
            s.ready ? (
              <Link
                key={s.key}
                href={s.href}
                aria-current={active === s.key ? "page" : undefined}
                className={cn(
                  "whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors",
                  active === s.key
                    ? "border-primary text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground",
                )}
              >
                {s.label}
              </Link>
            ) : (
              <span
                key={s.key}
                className="flex cursor-not-allowed items-center gap-1.5 whitespace-nowrap border-b-2 border-transparent px-3 py-2 text-sm font-medium text-muted-foreground/60"
                title="Ships in a later ticket"
              >
                {s.label}
                <Badge variant="muted" className="px-1 py-0 text-[10px]">
                  soon
                </Badge>
              </span>
            ),
          )}
        </nav>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">{children}</main>
    </div>
  );
}
