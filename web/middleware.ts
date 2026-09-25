import type { NextFetchEvent, NextRequest, NextResponse } from "next/server";

import { auth } from "@/auth";

// Route protection for the whole app. NextAuth runs the `authorized` callback (web/auth.ts) for
// every matched request: the public sign-in route is allowed; everything else requires a
// declared identity (v1 POC login — no password/OAuth), otherwise the request is redirected to
// /signin with a callbackUrl. This is the seam that makes the expert deep link identity-gated
// rather than an anonymous bypass.
export default function middleware(request: NextRequest, event: NextFetchEvent) {
  // Delegate to NextAuth's middleware. `auth`'s public overloads favor the pages-router
  // `NextApiRequest` signature; at runtime it accepts the App-Router `(NextRequest, event)` pair
  // (this is exactly `export { auth as middleware }`), so cast to that shape.
  return (auth as unknown as MiddlewareFn)(request, event);
}

type MiddlewareFn = (
  request: NextRequest,
  event: NextFetchEvent,
) => ReturnType<typeof NextResponse.next> | Promise<Response>;

export const config = {
  // Match every route EXCEPT:
  //  - /api/auth/*   → NextAuth's own OAuth/session endpoints (must stay reachable to sign in).
  //  - /api/health   → the container healthcheck hits this unauthenticated (docker-compose.yml).
  //  - /api/build    → public build-commit metadata (no auth, like health).
  //  - /.well-known/cmw-build.json → static baked build metadata (no auth, like health).
  //  - Next.js internals and static assets, and the favicon.
  matcher: ["/((?!api/auth|api/health|api/build|\.well-known/cmw-build\.json|_next/static|_next/image|favicon.ico).*)"],
};
