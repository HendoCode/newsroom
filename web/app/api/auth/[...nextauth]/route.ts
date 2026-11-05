import { handlers } from "@/auth";

// NextAuth's OAuth callback + session endpoints. The handlers come from the shared config in
// `web/auth.ts`; this route just exposes them to the App Router (docs/design.md D10, §6).
export const { GET, POST } = handlers;
