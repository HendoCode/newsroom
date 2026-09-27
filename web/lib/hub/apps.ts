import { Sparkles, type LucideIcon } from "lucide-react";

/**
 * The post-login app hub's app catalog (`app/page.tsx`, `components/hub/app-hub.tsx`). This is
 * deliberately DATA, not layout — adding a future app is a one-line addition here, never a hub
 * layout rewrite. Newsroom is the only real, enabled entry today; `enabled: false` is the
 * seam a future in-progress app can use to appear (e.g. visibly disabled) before it's ready,
 * without touching `AppHub`'s rendering.
 */
export interface HubApp {
  id: string;
  name: string;
  blurb: string;
  icon: LucideIcon;
  href: string;
  enabled: boolean;
}

export const HUB_APPS: HubApp[] = [
  {
    id: "content-machine",
    name: "Newsroom",
    blurb:
      "Turn interviews and source material into on-voice drafts, run them through council review, and ship finalized pieces.",
    icon: Sparkles,
    href: "/content-machine",
    enabled: true,
  },
];
