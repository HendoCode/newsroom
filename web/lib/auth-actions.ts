"use server";

import { signIn, signOut } from "@/auth";

/**
 * Server actions for the auth UI. NextAuth's `signIn`/`signOut` run server-side only; client
 * components (the identity login form, the sign-out button) invoke these so no provider config
 * touches the browser.
 */

/**
 * Sign in as the declared identity from the login form (email + optional display name). No
 * password, no OAuth round trip — `web/auth.ts`'s Credentials provider IS the check, and it
 * accepts any well-formed email. Returns to `callbackUrl` (the deep link the user was gated from).
 * Only reachable when Google isn't configured (`web/auth.ts` doesn't register this provider
 * otherwise) — see the `/signin` screen for which form renders.
 */
export async function signInWithIdentity(
  callbackUrl: string | undefined,
  formData: FormData,
): Promise<void> {
  const email = formData.get("email");
  const name = formData.get("name");
  await signIn("identity", {
    email: typeof email === "string" ? email : "",
    name: typeof name === "string" ? name : "",
    redirectTo: callbackUrl && callbackUrl.length > 0 ? callbackUrl : "/",
  });
}

/**
 * Start the Google OAuth round trip. Domain restriction happens in `web/auth.ts`'s `signIn`
 * callback, not here — this just kicks off the redirect to Google's consent screen.
 */
export async function signInWithGoogle(callbackUrl: string | undefined): Promise<void> {
  await signIn("google", {
    redirectTo: callbackUrl && callbackUrl.length > 0 ? callbackUrl : "/",
  });
}

/** Sign out and return to the identity login page. */
export async function signOutAction(): Promise<void> {
  await signOut({ redirectTo: "/signin" });
}
