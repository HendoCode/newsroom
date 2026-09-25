/**
 * The desk layout model — the dashboard redesigned as **Inbox + Machine strip + Library**
 * (Concept A "operator desk", cmw-evolution-ux-audit report §6/§7, captain-approved 2026-08-31).
 *
 * One shared queue in, three honest sections out:
 *
 *  - **Inbox** — ONLY real human-actionable decisions, grouped by the decision itself
 *    ("Answer — you're the expert", "Decide: enough input?", …). Built on the expanded
 *    `needsMyAction` predicate (PR #140) consumed UNCHANGED: every item the predicate puts on a
 *    plate lands in exactly one group, except the one branch that is not actually a decision
 *    (see `decisionGroupFor`).
 *  - **Machine strip** — ambient visibility of what the machine is currently running (batch
 *    stages: drafting / council / incorporating / finalizing, no failed jobs). Not a list you
 *    click into — the audit §6 rule: "Not in the inbox: batch-running jobs (those are a
 *    'machine is working' strip)."
 *  - **Library** — every piece across every stage (published/finalized included), filterable,
 *    nothing hidden, with honest in-flight-vs-terminal counts (the old "All in flight" tab
 *    included `published` and lied about it — report §2.3).
 *
 * Everything here is a pure, total function of `(items, email)` so it is trivially unit-tested.
 *
 * SYNC DISCIPLINE: `decisionGroupFor` mirrors `needs-my-action.ts`'s branch structure 1:1. If a
 * future change adds a predicate branch, extend this module's stage map in the SAME commit — an
 * unclassified predicate hit is a silent drop, exactly the gap this module exists to close.
 * `desk.test.ts`'s no-loss test is the tripwire.
 */

import { statusOf } from "@/lib/dashboard/filters";
import { needsMyAction, type NeedsActionResult } from "@/lib/dashboard/needs-my-action";
import type { PieceStage, QueueItem } from "@/lib/dashboard/types";
import { isBatchStage } from "@/lib/pieces/stage";

/** The decision types the Inbox groups by (report §6's list; display order is this order). */
export type DecisionGroup =
  | "answer" // Answer — you're the expert
  | "enough-input" // Decide: enough input?
  | "review-round" // Review / close a round
  | "sign-off" // Sign off / publish
  | "lessons" // Accept / reject lessons
  | "recover" // Recover a failure
  | "pick-spike" // Pick a spike
  // Resume a paused piece — NOT in the report's seven: the settled predicate (PR #140) has a
  // paused+owner branch whose decision ("resume when you are ready") fits none of the seven,
  // and mislabelling it as a failure would be worse than one extra group.
  | "resume";

export interface DecisionGroupDef {
  key: DecisionGroup;
  label: string;
  /** One line naming the decision itself — rendered under the group heading. */
  description: string;
}

/** The settled groups in display order (the report §6 order; `resume` appended last). */
export const DECISION_GROUPS: DecisionGroupDef[] = [
  {
    key: "answer",
    label: "Answer — you’re the expert",
    description: "An interview is assigned to you — accept the invite and answer its pending question.",
  },
  {
    key: "enough-input",
    label: "Decide: enough input?",
    description: "Interviews came back — read the transcript, then decide whether there's enough to draft or send a follow-up.",
  },
  {
    key: "review-round",
    label: "Review / close a round",
    description: "A draft awaits your comb — mint or close the review round, or finalize.",
  },
  {
    key: "sign-off",
    label: "Sign off / publish",
    description: "A finalized piece is ready — the irreversible publish is your call.",
  },
  {
    key: "lessons",
    label: "Accept / reject lessons",
    description: "Proposed voice lessons from a piece — accept, edit, or reject each one.",
  },
  {
    key: "recover",
    label: "Recover a failure",
    description: "A job you triggered failed — the piece stayed at its last stable stage; retry or edit inputs.",
  },
  {
    key: "pick-spike",
    label: "Pick a spike",
    description: "A picked idea has no expert / kickoff yet — assign one and open the first interview.",
  },
  {
    key: "resume",
    label: "Resume a paused piece",
    description: "A piece you own is paused — resume it when you are ready.",
  },
];

/**
 * Owner-at-stage classification for the owner branches of the predicate (branches 3–5, 7–11),
 * exhaustive over every `PieceStage` so a future stage cannot silently classify to nothing.
 * `null` = not an inbox decision: `incorporating` is the predicate's branch 7, whose own why-text
 * says "wait for it, or check progress" — a running job belongs on the machine strip, not the inbox
 * (audit §6). The batch stages the predicate never matches for an owner are `null` for the same
 * reason; `published` is terminal — the predicate never matches it.
 */
const OWNER_STAGE_GROUPS: Record<PieceStage, DecisionGroup | null> = {
  interviewing: "enough-input", // branches 3 (complete interview) and 4 (GAP loop-back)
  drafting: null,
  council: null,
  review: "review-round", // branch 5
  incorporating: null, // branch 7 → machine strip
  finalizing: null,
  finalized: null, // branches 9/10 — disambiguated on lessons_proposed in decisionGroupFor
  lessons: "lessons", // branch 11
  paused: "resume", // branch 8
  released: null,
  published: null,
};

/**
 * Which inbox decision group a predicate hit belongs to — or `null` when it belongs on the
 * machine strip instead (a batch-running piece, e.g. the predicate's incorporating+owner branch).
 * Mirrors `needs-my-action.ts`'s branch precedence so the group never contradicts the "why here"
 * text the predicate returned alongside it. Pure and total: a spike hit is always `pick-spike`.
 */
export function decisionGroupFor(item: QueueItem, needs: NeedsActionResult): DecisionGroup | null {
  // The predicate checks the failed-job branch FIRST, regardless of stage.
  if (needs.relationship === "last-actor") return "recover";
  if (needs.relationship === "assigned-expert") return "answer";

  if (item.kind === "spike") return "pick-spike"; // the predicate's only spike branch

  // Owner branches — disambiguate by stage, mirroring the predicate.
  if (item.stage === "finalized") {
    return item.lessons_proposed > 0 ? "lessons" : "sign-off";
  }
  return OWNER_STAGE_GROUPS[item.stage ?? "published"];
}

/** One inbox row: the queue item, the predicate's attribution result, and its decision group. */
export interface InboxEntry {
  item: QueueItem;
  needs: NeedsActionResult;
  group: DecisionGroup;
}

/** A non-empty inbox group, in the settled display order of {@link DECISION_GROUPS}. */
export interface InboxGroup {
  def: DecisionGroupDef;
  entries: InboxEntry[];
}

/**
 * Group every human-actionable queue item by its decision. Consumes `needsMyAction` unchanged;
 * items whose only claim on attention is a running job classify to `null` here and surface on
 * the machine strip instead — nothing the predicate puts on a plate is dropped by this module
 * (see the no-loss test in `desk.test.ts`). Empty groups are omitted; a falsy email yields [].
 */
export function buildInbox(items: QueueItem[], email: string | null | undefined): InboxGroup[] {
  const byGroup = new Map<DecisionGroup, InboxEntry[]>();
  for (const item of items) {
    const needs = needsMyAction(email, item);
    if (!needs) continue;
    const group = decisionGroupFor(item, needs);
    if (!group) continue; // batch-running — the machine strip shows it
    const list = byGroup.get(group) ?? [];
    list.push({ item, needs, group });
    byGroup.set(group, list);
  }
  return DECISION_GROUPS.filter((def) => byGroup.has(def.key)).map((def) => ({
    def,
    entries: byGroup.get(def.key)!,
  }));
}

/**
 * The machine strip's data: pieces currently RUNNING a batch job — batch stage, no failed job
 * (a failed job stopped the machine; that's a Recover decision in the inbox, not movement).
 * Deliberately not clickable at the call site: ambient visibility, not a queue (audit §6).
 */
export function machineWorking(items: QueueItem[]): QueueItem[] {
  return items.filter(
    (it) => it.kind === "piece" && it.stage !== null && isBatchStage(it.stage) && !it.failed_job,
  );
}

/** The Library is pieces only — spikes are candidate ideas and live on their own `/spikes` page
 * (the duplicate dashboard Spikes tab this redesign killed). */
export function libraryPieces(items: QueueItem[]): QueueItem[] {
  return items.filter((it) => it.kind === "piece");
}

export interface LibrarySummary {
  total: number;
  inFlight: number;
  done: number;
  failed: number;
}

/**
 * Honest in-flight-vs-terminal counts for the Library header (`statusOf` is the coarse axis that
 * knows `published`/`finalized`/`lessons` are done — the old "All in flight" tab did not use it
 * and counted 13/13 pieces as in flight).
 */
export function librarySummary(items: QueueItem[]): LibrarySummary {
  const pieces = libraryPieces(items);
  let inFlight = 0;
  let done = 0;
  let failed = 0;
  for (const p of pieces) {
    const s = statusOf(p);
    if (s === "done") done += 1;
    else if (s === "failed") failed += 1;
    else inFlight += 1;
  }
  return { total: pieces.length, inFlight, done, failed };
}
