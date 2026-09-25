import { describe, expect, it } from "vitest";

import { primaryAction } from "@/lib/dashboard/actions";
import type { QueueItem } from "@/lib/dashboard/types";

/** A neutral spike item; override per test. */
function spike(overrides: Partial<QueueItem> = {}): QueueItem {
  return {
    kind: "spike",
    id: "s1",
    title: "A spike",
    voice: null,
    stage: null,
    spike_status: "proposed",
    owner: null,
    assigned_experts: [],
    creator: "someone@example.com",
    council_aggregate: null,
    open_gaps: 0,
    open_clearances: 0,
    review_round: null,
    open_interviews: [],
    has_complete_interview: false,
    failed_job: null,
    lessons_proposed: 0,
    spike_assigned: false,
    updated_at: null,
    last_human_touch_at: null,
    ...overrides,
  };
}

describe("primaryAction — the spike-card label (Hendo: an already-picked spike must not read as unpicked)", () => {
  it("offers 'Assign expert & kick off' for a spike nobody has picked yet", () => {
    const item = spike({ spike_status: "proposed", spike_assigned: false });
    expect(primaryAction(item, null, null).label).toBe("Assign expert & kick off");
  });

  it("offers a different label once the spike is picked and already has its piece", () => {
    const item = spike({ spike_status: "picked", spike_assigned: true });
    const action = primaryAction(item, null, null);
    expect(action.label).not.toBe("Assign expert & kick off");
    expect(action.label).toBe("Continue kickoff");
    // Same destination either way — the kickoff screen itself tells the two cases apart.
    expect(action.href).toBe("/spikes/s1");
  });

  it("offers 'Re-consider' for a vaulted spike (deferred, not proposed — 'Assign expert & kick off' reads as a fresh candidate)", () => {
    const item = spike({ spike_status: "vaulted", spike_assigned: false });
    expect(primaryAction(item, null, null).label).toBe("Re-consider");
    expect(primaryAction(item, null, null).href).toBe("/spikes/s1");
  });
});
