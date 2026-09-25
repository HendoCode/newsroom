/**
 * Native derivative formats for an anchor piece (cmw-repurposing-derivatives-ia).
 *
 * Lieberman / the evolution synthesis: one anchor → n natives, each a real Piece with its own
 * council bar — never a re-render of the same text (HTML/PDF/Doc stay render formats, not
 * Pieces). Generation is not built yet; this catalog is the target IA so publish stops looking
 * like the last step.
 *
 * Destinations named in the synthesis (LinkedIn post, X thread, newsletter) plus the Content
 * Project default (`blog`) and a small set of other natives the deferred §9 distribution effort
 * already named (email) or that the operator desk already treats as first-class channels.
 * Matching is by `destination` string on an existing derivative Piece — aliases absorb the
 * free-form `anchor_destination` values `commit-idea` currently accepts.
 */

export type DerivativeFormatId =
  | "linkedin-post"
  | "linkedin-carousel"
  | "x-thread"
  | "newsletter"
  | "blog"
  | "executive-brief"
  | "talk-track"
  | "email";

export interface DerivativeFormat {
  id: DerivativeFormatId;
  label: string;
  blurb: string;
  /** Destination strings that mean this format, including the canonical id itself. */
  destinations: readonly string[];
}

export const DERIVATIVE_FORMATS: readonly DerivativeFormat[] = [
  {
    id: "linkedin-post",
    label: "LinkedIn post",
    blurb: "Re-hooked for the feed. Own quality cycle — the anchor’s score does not certify this.",
    destinations: ["linkedin-post", "linkedin", "li"],
  },
  {
    id: "linkedin-carousel",
    label: "LinkedIn carousel",
    blurb: "Slide-native argument. Commissioned as its own Piece, not a PDF of the anchor.",
    destinations: ["linkedin-carousel", "carousel"],
  },
  {
    id: "x-thread",
    label: "X thread",
    blurb: "Beat-by-beat thread. Own hook and own bar; a sensational opener can fail while the newsletter passes.",
    destinations: ["x-thread", "x", "twitter", "twitter-thread"],
  },
  {
    id: "newsletter",
    label: "Newsletter",
    blurb: "Audience-native intro and through-line. Independent of the LinkedIn Piece on the same project.",
    destinations: ["newsletter"],
  },
  {
    id: "blog",
    label: "Blog post",
    blurb: "Long-form native. The Content Project default destination when an idea is committed.",
    destinations: ["blog", "blog-post"],
  },
  {
    id: "executive-brief",
    label: "Executive brief",
    blurb: "Short brief for a decision-maker. Own claims and own clearances.",
    destinations: ["executive-brief", "brief", "whitepaper", "white-paper"],
  },
  {
    id: "talk-track",
    label: "Talk track",
    blurb: "Spoken native — what the voice actually says. Not a paste of the blog.",
    destinations: ["talk-track", "talk", "speaker-notes"],
  },
  {
    id: "email",
    label: "Email",
    blurb: "Send-native. Channel publication (what actually went out) is a later record.",
    destinations: ["email", "email-update"],
  },
] as const;

export type DerivativeLineage = "child" | "promoted";

export interface ExistingDerivative {
  id: string;
  title: string;
  destination: string;
  /** Operator-facing phase/status, when the workspace has one (Piece Studio `derived_phase`). */
  phase?: string;
  href?: string;
  /** Child of the anchor by default; promoted to a top-level Piece when it needs its own
   * owner/review/publish state. Absent/undefined means child (the default). */
  lineage?: DerivativeLineage;
  promoted_piece_id?: string | null;
  /** Council-quality bar for this derivative (cmw-derivative-quality-bar-impl). */
  quality?: DerivativeQuality;
}

export interface DerivativeArtifact {
  id: string;
  anchor_piece_id: string;
  content_project_id: string | null;
  destination: string;
  title: string;
  voice: string | null;
  lineage: DerivativeLineage;
  promoted_piece_id: string | null;
  quality?: DerivativeQuality;
}

export function existingFromArtifact(artifact: DerivativeArtifact): ExistingDerivative {
  return {
    id: artifact.id,
    title: artifact.title,
    destination: artifact.destination,
    lineage: artifact.lineage,
    promoted_piece_id: artifact.promoted_piece_id,
    quality: artifact.quality,
    href:
      artifact.lineage === "promoted" && artifact.promoted_piece_id
        ? `/pieces/${encodeURIComponent(artifact.promoted_piece_id)}`
        : undefined,
  };
}

export function lineageOf(derivative: ExistingDerivative): DerivativeLineage {
  return derivative.lineage ?? "child";
}

/** Href for a promoted derivative's own piece page; children have none. */
export function promotedHref(derivative: ExistingDerivative): string | undefined {
  if (lineageOf(derivative) !== "promoted") return undefined;
  if (derivative.href) return derivative.href;
  const pieceId = derivative.promoted_piece_id ?? derivative.id;
  return pieceId ? `/pieces/${encodeURIComponent(pieceId)}` : undefined;
}

export type DerivativeSlot =
  | {
      kind: "existing";
      format: DerivativeFormat | null;
      derivative: ExistingDerivative;
    }
  | {
      kind: "creatable";
      format: DerivativeFormat;
    };

const DESTINATION_INDEX: ReadonlyMap<string, DerivativeFormat> = (() => {
  const map = new Map<string, DerivativeFormat>();
  for (const format of DERIVATIVE_FORMATS) {
    for (const dest of format.destinations) {
      map.set(dest.toLowerCase(), format);
    }
  }
  return map;
})();

export function formatForDestination(destination: string): DerivativeFormat | null {
  const key = destination.trim().toLowerCase();
  if (!key) return null;
  return DESTINATION_INDEX.get(key) ?? null;
}

/**
 * Split the catalog into existing vs still-creatable slots for one anchor.
 *
 * An existing derivative whose destination matches a catalog format occupies that format (it
 * does not also appear as creatable). Unknown destinations still surface as existing — never
 * dropped — with `format: null` so the UI can label them from the raw destination.
 */
export function derivativeSlots(existing: readonly ExistingDerivative[]): DerivativeSlot[] {
  const taken = new Set<DerivativeFormatId>();
  const slots: DerivativeSlot[] = [];

  for (const derivative of existing) {
    const format = formatForDestination(derivative.destination);
    if (format) taken.add(format.id);
    slots.push({ kind: "existing", format, derivative });
  }

  for (const format of DERIVATIVE_FORMATS) {
    if (taken.has(format.id)) continue;
    slots.push({ kind: "creatable", format });
  }

  return slots;
}

export const COMMISSION_NOT_BUILT_REASON =
  "Native generation is not built yet. Commission records a child artifact of this piece — promote it to its own piece when it needs its own owner, review, or publish.";

export const COMMISSION_CHILD_REASON =
  "Adds a child artifact of this piece. Native generation is not built yet — promote it to its own piece when it needs its own owner, review, or publish.";

/**
 * Derivative quality bar (cmw-derivative-quality-bar-impl). Every publishable native derivative
 * must clear ITS OWN council at DERIVATIVE_QUALITY_BAR with a destination-specific editor lineup
 * (a LinkedIn post and a whitepaper need different judgment), while UNIVERSAL_HARD_GATES apply to
 * every destination. This is the display mirror of `agents/app/derivatives/quality.py` — keep
 * the two in sync (same canonical ids, same aliases as DERIVATIVE_FORMATS above).
 */
export const DERIVATIVE_QUALITY_BAR = 9;

/** Universal hard gates applied to every destination regardless of its lineup. */
export const UNIVERSAL_HARD_GATES = ["facts", "safety"] as const;
export type UniversalHardGate = (typeof UNIVERSAL_HARD_GATES)[number];

/** Mandatory council members + the universal-gate editors present on every derivative council. */
export const UNIVERSAL_COUNCIL_EDITORS = [
  "slop-allergist",
  "voice-guardian",
  "technical-reviewer",
] as const;

/** Destination-specific judgment (editor persona names from the brain). */
export const DESTINATION_COUNCIL_EDITORS: Readonly<Record<DerivativeFormatId, readonly string[]>> = {
  "linkedin-post": ["puri", "cold-reader", "closer"],
  "linkedin-carousel": ["puri", "structure-editor"],
  "x-thread": ["puri", "closer", "cold-reader"],
  newsletter: ["perell", "cold-reader", "closer"],
  blog: ["structure-editor", "perell", "specificity-auditor"],
  "executive-brief": ["specificity-auditor", "structure-editor", "housel"],
  "talk-track": ["closer", "cold-reader"],
  email: ["perell", "puri"],
};

export const DEFAULT_COUNCIL_EDITORS = ["cold-reader", "structure-editor"] as const;

/**
 * The full council lineup for a derivative destination: mandatory editors + universal-gate editors
 * + the destination's judgment, deduped in that precedence order. Mirrors
 * `agents.app.derivatives.quality.derivative_council_editors`.
 */
export function derivativeCouncilEditors(destination: string): readonly string[] {
  const format = formatForDestination(destination);
  const fit = format ? DESTINATION_COUNCIL_EDITORS[format.id] : DEFAULT_COUNCIL_EDITORS;
  const lineup: string[] = [...UNIVERSAL_COUNCIL_EDITORS];
  for (const editor of fit) {
    if (!lineup.includes(editor)) lineup.push(editor);
  }
  return lineup;
}

/** The council-quality state for one derivative, projected by the backend for this surface. */
export interface DerivativeQuality {
  required: boolean;
  cleared: boolean;
  bar: number;
  aggregate: number | null;
  council_revision: string | null;
  reasons: string[];
  editors: string[];
  universal_gates: UniversalHardGate[];
}
