/**
 * The v1 POC identity-declaration login (docs/design.md §6 "Auth"; domain model §1.17).
 *
 * There is no password or OAuth check: anyone can sign in as any (pretend) identity by declaring
 * an email (+ optional display name). This module is the pure, unit-tested rule for turning that
 * free-form declaration into a well-formed identity — no NextAuth, no network — so both the
 * Credentials `authorize()` call (`web/auth.ts`) and any future caller can reuse it.
 */

export interface Identity {
  /** Normalized (trimmed, lowercased) email — the identity key (domain model §1.17). */
  email: string;
  /** Trimmed display name, or null when not supplied. */
  name: string | null;
}

/** A bare-minimum "looks like an email" shape check — not verification, just unusable-input filtering. */
const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Parse a declared identity from raw (untrusted, possibly non-string) form input.
 *
 * Returns null only when the email is missing/blank or doesn't look like an email at all — every
 * other input is accepted as-is (this is a POC declaration, not real verification).
 */
export function parseIdentity(input: { email?: unknown; name?: unknown }): Identity | null {
  const email = normalizeEmail(input.email);
  if (!email) return null;
  return { email, name: normalizeName(input.name) };
}

function normalizeEmail(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim().toLowerCase();
  return EMAIL_SHAPE.test(trimmed) ? trimmed : null;
}

function normalizeName(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}
