"use client";

/** The non-blocking "courtesy note" (D12; cmw-ui-wireframes screen 11): a heads-up, never a gate,
 * shown when editing a voice that isn't the signed-in user's own. */
export function CourtesyNote({ voice }: { voice: string }) {
  return (
    <p
      role="status"
      className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-foreground"
    >
      <span className="font-semibold">Courtesy note</span> — you&rsquo;re editing{" "}
      <b>{voice}</b>&rsquo;s voice kit and it doesn&rsquo;t look like your own. That&rsquo;s
      allowed — Git is the reversible safety net (D12) — just a heads-up, not a gate.
    </p>
  );
}
