import { Sparkles } from "lucide-react";

import { signInWithGoogle, signInWithIdentity } from "@/lib/auth-actions";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  getGoogleAuthConfig,
  resolveAllowedEmailDomain,
  signInErrorMessage,
} from "@/lib/google-auth";

// Public sign-in screen (docs/design.md §6 "Auth"; docs/auth.md). Two mutually exclusive modes,
// matching the providers `web/auth.ts` registers:
//  - Google configured (real deployments): a single "Sign in with Google" button, restricted to
//    `AUTH_ALLOWED_EMAIL_DOMAIN` (enforced server-side in auth.ts's `signIn` callback — this
//    screen just kicks off the OAuth redirect).
//  - Google not configured (local dev with no creds): the identity-declaration form — no
//    password, no OAuth. Declaring a well-formed email signs you in as that (pretend) identity.
// Unauthenticated access anywhere else is redirected here with a `callbackUrl`, so signing in
// returns the user to the deep link they were gated from (e.g. an expert interview link).
export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ callbackUrl?: string; error?: string }>;
}) {
  const { callbackUrl, error } = await searchParams;
  const google = await getGoogleAuthConfig();
  const allowedEmailDomain = resolveAllowedEmailDomain(process.env.AUTH_ALLOWED_EMAIL_DOMAIN);

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-8 px-6 py-12">
      <div className="flex flex-col items-center gap-2 text-center">
        <span className="flex h-11 w-11 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <Sparkles className="h-6 w-6" aria-hidden />
        </span>
        <span className="font-serif text-xl font-semibold">Newsroom</span>
      </div>

      <Card className="w-full">
        <CardHeader className="text-center">
          <CardTitle>Sign in</CardTitle>
          <CardDescription>
            {google
              ? allowedEmailDomain
                ? `Sign in with your @${allowedEmailDomain} Google Workspace account.`
                : "Sign in with your verified Google account."
              : "v1 POC — no password or Google account needed. Tell us who you are and you're in."}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {error ? <Alert>{signInErrorMessage(error, google, allowedEmailDomain)}</Alert> : null}
          {google ? (
            <form action={signInWithGoogle.bind(null, callbackUrl)}>
              <Button type="submit" className="w-full">
                Sign in with Google
              </Button>
            </form>
          ) : (
            <form action={signInWithIdentity.bind(null, callbackUrl)} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5 text-left">
                <label htmlFor="email" className="text-sm font-medium leading-none">
                  Email
                </label>
                <Input
                  id="email"
                  name="email"
                  type="email"
                  placeholder="you@example.com"
                  autoComplete="email"
                  autoFocus
                  required
                />
              </div>
              <div className="flex flex-col gap-1.5 text-left">
                <label htmlFor="name" className="text-sm font-medium leading-none">
                  Display name <span className="text-muted-foreground">(optional)</span>
                </label>
                <Input
                  id="name"
                  name="name"
                  type="text"
                  placeholder="Jane Doe"
                  autoComplete="name"
                />
              </div>
              <Button type="submit" className="w-full">
                Continue
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
