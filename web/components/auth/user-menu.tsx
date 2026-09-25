import { LogOut } from "lucide-react";

import { signOutAction } from "@/lib/auth-actions";
import type { AppUser } from "@/lib/session";
import { Button } from "@/components/ui/button";

/**
 * Authenticated app-shell control: shows who is signed in and offers sign-out. Rendered in the
 * header of protected pages. Attribution only — it displays identity, it does not gate anything
 * by role (authorization is flat; domain model §1.17, design.md §2).
 */
export function UserMenu({ user }: { user: AppUser }) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex flex-col items-end leading-tight">
        {user.name ? (
          <span className="text-sm font-medium">{user.name}</span>
        ) : null}
        <span className="text-xs text-muted-foreground">{user.email}</span>
      </div>
      <form action={signOutAction}>
        <Button type="submit" variant="outline" size="sm">
          <LogOut className="mr-2 h-4 w-4" aria-hidden />
          Sign out
        </Button>
      </form>
    </div>
  );
}
