import { describe, expect, it } from "vitest";

import { HUB_APPS } from "@/lib/hub/apps";

describe("HUB_APPS", () => {
  it("lists Newsroom as a real, enabled entry routing into the existing app", () => {
    const newsroomApp = HUB_APPS.find((app) => app.id === "newsroom");
    expect(newsroomApp).toBeDefined();
    expect(newsroomApp?.enabled).toBe(true);
    expect(newsroomApp?.href).toBe("/newsroom");
    expect(newsroomApp?.name).toBe("Newsroom");
    expect(newsroomApp?.blurb.length).toBeGreaterThan(0);
  });

  it("gives every entry the fields AppHub needs to render a card", () => {
    for (const app of HUB_APPS) {
      expect(app.id).toBeTruthy();
      expect(app.name).toBeTruthy();
      expect(app.blurb).toBeTruthy();
      expect(app.href).toBeTruthy();
      expect(app.icon).toBeTruthy();
      expect(typeof app.enabled).toBe("boolean");
    }
  });

  it("has no duplicate ids", () => {
    const ids = HUB_APPS.map((app) => app.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});
