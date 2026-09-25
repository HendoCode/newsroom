/**
 * The non-blocking "courtesy note" predicate (D12; cmw-ui-wireframes screen 11): any employee may
 * edit any voice kit — this never gates anything, it only decides whether to show a heads-up that
 * you're editing someone else's kit. `demo-dana` is shared by everyone, so it never triggers the
 * note.
 *
 * There is no formal Voice-to-User mapping in the domain model (§1.17 attribution is
 * piece/spike-scoped, not voice-scoped) — this is a best-effort match against the signed-in
 * user's email/name, exactly the kind of heuristic a non-blocking convenience note can afford.
 */

const TEAM_VOICE_SLUGS = new Set(["demo-dana", "team"]);

export function isOwnVoice(
  voiceSlug: string,
  user: { email?: string | null; name?: string | null } | null | undefined,
): boolean {
  if (TEAM_VOICE_SLUGS.has(voiceSlug)) return true;
  if (!user) return false;
  const slug = voiceSlug.toLowerCase();
  const localPart = user.email?.split("@")[0]?.toLowerCase();
  if (localPart && (localPart === slug || localPart.startsWith(`${slug}.`))) return true;
  const name = user.name?.toLowerCase().replace(/\s+/g, "");
  if (name && (name === slug || name.startsWith(slug))) return true;
  return false;
}
