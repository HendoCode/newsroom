import { redirect } from "next/navigation";

import { auth } from "@/auth";

/**
 * The typed way the rest of the app reads the signed-in user (docs/design.md §6 "Auth"; domain
 * model §1.17 "User / Identity").
 *
 * `AppUser` is the session model as product code should consume it: the declared email identity
 * plus a display name (v1 POC: `web/auth.ts`'s identity-declaration login — no password/OAuth).
 * Per the domain model, role labels are attribution-only and authorization is FLAT — so roles are
 * deliberately absent here. Any signed-in identity can act on any piece; do NOT reintroduce
 * per-role gates on top of this accessor. `image` stays in the shape (always null for now) so a
 * later real OAuth swap-back (`web/auth.ts`) needs no changes downstream.
 */
export interface AppUser {
  /** Declared email — the identity key backing the durable Mongo user record (§1.17). */
  email: string;
  /** Declared display name; may be absent. */
  name: string | null;
  /** Avatar URL; always null under the POC identity login. */
  image: string | null;
}

/** Read the current user, or null when unauthenticated. Use in server components / route handlers. */
export async function getCurrentUser(): Promise<AppUser | null> {
  const session = await auth();
  const user = session?.user;
  // Email is the identity key; a session without one is not a usable signed-in user.
  if (!user?.email) return null;
  return {
    email: user.email,
    name: user.name ?? null,
    image: user.image ?? null,
  };
}

/**
 * Require a signed-in user, redirecting to the identity login page otherwise. This is the guard
 * for authenticated server components (the app shell, the expert deep link). Middleware already
 * gates these routes; calling this is cheap defense-in-depth and yields a typed user.
 */
export async function requireUser(): Promise<AppUser> {
  const user = await getCurrentUser();
  if (!user) {
    redirect("/signin");
  }
  return user;
}
