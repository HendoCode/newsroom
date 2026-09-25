import { describe, expect, it } from "vitest";

import { draftExcerpt, parseDraftHtml, plainTextLength } from "@/lib/pieces/draft-html";

const REAL_SHAPE = `<!DOCTYPE html>
<html lang="en">
<head><title>t</title></head>
<body>
<h1>Title</h1>
<p>Some content.</p>

<section class="editorial" aria-label="Editorial annotations, not for publication">
  <h3>Editorial annotations — remove before publishing</h3>
  <p><span class="tag">[GAP]</span> Something is missing.</p>
</section>

</body>
</html>`;

describe("parseDraftHtml — splits the publishable body from the editorial block", () => {
  it("extracts the editorial section's inner HTML and removes it from the body", () => {
    const { bodyHtml, editorialHtml } = parseDraftHtml(REAL_SHAPE);
    expect(bodyHtml).toContain("<h1>Title</h1>");
    expect(bodyHtml).not.toContain("editorial");
    expect(bodyHtml).not.toContain("[GAP]");
    expect(editorialHtml).toContain("[GAP]");
    expect(editorialHtml).toContain("remove before publishing");
  });

  it("returns null editorialHtml when there is no editorial section", () => {
    const { bodyHtml, editorialHtml } = parseDraftHtml("<html><body><p>plain</p></body></html>");
    expect(bodyHtml).toBe("<p>plain</p>");
    expect(editorialHtml).toBeNull();
  });

  it("falls back to the whole string when there is no <body> tag", () => {
    const { bodyHtml, editorialHtml } = parseDraftHtml("<p>fragment only</p>");
    expect(bodyHtml).toBe("<p>fragment only</p>");
    expect(editorialHtml).toBeNull();
  });
});

describe("plainTextLength — the size signal behind DraftView's tweet-vs-long-form clamp", () => {
  it("strips tags and collapses whitespace before counting", () => {
    expect(plainTextLength("<p>hello   <b>world</b></p>")).toBe("hello world".length);
  });

  it("counts a tweet-sized fragment as short", () => {
    const tweet = "<p>Three customer conversations converged on the same theme this week.</p>";
    expect(plainTextLength(tweet)).toBeLessThan(200);
  });
});

describe("draftExcerpt — collapsed-card summary of what the piece says", () => {
  it("returns the whole plain text when it is already short", () => {
    expect(draftExcerpt("<h1>Amazon Quick + Hendo</h1><p>A seller brief.</p>")).toBe(
      "Amazon Quick + Hendo A seller brief.",
    );
  });

  it("truncates on a word boundary and adds an ellipsis", () => {
    const html = `<p>${"word ".repeat(40).trim()}</p>`;
    const excerpt = draftExcerpt(html, 20);
    expect(excerpt.endsWith("…")).toBe(true);
    expect(excerpt.length).toBeLessThanOrEqual(21);
    expect(excerpt).not.toMatch(/\s…$/);
  });

  it("returns empty for empty HTML", () => {
    expect(draftExcerpt("   ")).toBe("");
    expect(draftExcerpt("<p></p>")).toBe("");
  });
});
