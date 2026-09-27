import { Sparkles } from "lucide-react";

import { UserMenu } from "@/components/auth/user-menu";
import { ThemeToggle } from "@/components/theme-toggle";
import type { AppUser } from "@/lib/session";

/**
 * The focused frame for the interviewee's interview surface (`/interviews/[interviewId]`, the
 * SSO-gated deep link an external expert opens from a shared Slack link). Deliberately a slimmer
 * sibling of `AppShell`, not a flag on it: no section nav (Dashboard / Content projects / Radar /
 * Spikes & Vault / Sources / Voice kits) — the person here is mid-interview, usually on a phone,
 * and none of those sections are part of answering questions. Brand mark, theme toggle, and the
 * account menu stay, since the route is still behind the same sign-in gate.
 *
 * The interview content itself is single-column and mobile-first (`max-w-2xl`); everything is
 * token-driven like `AppShell` (re-skin via `globals.css`, never brand literals here).
 *
 * The brand mark is deliberately NOT a link: the one back-to-dashboard affordance is the
 * explicit "← Back to dashboard" control in `interview-surface-view.tsx`, so the exit is a
 * single, unambiguous place rather than two.
 */
export function InterviewShell({
  user,
  children,
}: {
  user: AppUser;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex w-full max-w-2xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <span aria-label="Newsroom" className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <Sparkles className="h-4 w-4" aria-hidden />
            </span>
            <span className="font-serif text-base font-semibold">Newsroom</span>
          </span>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <UserMenu user={user} />
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-6 sm:px-6 sm:py-8">{children}</main>
    </div>
  );
}
