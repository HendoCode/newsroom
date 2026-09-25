# Hendo Code Visual Identity

> Canonical visual system for Hendo Code content — the Hendo Code team's personal
> consultancy and technical blog. Use this whenever a piece renders as HTML
> (draft.html), a deck, a social graphic, or any visual artifact. Voice/copy rules
> live in `voice-guide.md` and `brand-guidelines.md`; this file governs **look**, not
> words.

---

## 1. Aesthetic

Clean, technical, and calm. The palette is built on **slate, amber, and cream** —
the same design language as hendocode.com. It feels like a field engineer's notebook,
not a corporate dashboard: slate for structure, amber for emphasis, cream for the page.

**Key words:** slate, amber, cream, technical, calm, precise.

**Anti-patterns (never):** neon accents, generic SaaS blue, gradients-as-decoration,
dark mode by default.

---

## 2. Color Palette

| Role | Name | Hex | HSL | Use |
|------|------|-----|-----|-----|
| **Primary** | Slate | `#2E4A5F` | `hsl(206, 35%, 28%)` | Headings, buttons, active states, links |
| **Accent** | Amber | `#E8A44A` | `hsl(34, 77%, 60%)` | Highlights, emphasis, secondary CTAs |
| **Background** | Warm cream | `#f5f2ea` | `hsl(44, 35%, 94%)` | Page background — **never white, never gray** |
| **Card** | Light cream | `#f8f6f0` | `hsl(45, 36%, 96%)` | Card / panel fills |
| **Text** | Slate-dark | `#1e3245` | `hsl(209, 39%, 19%)` | Primary text — **never pure black `#000`** |
| **Muted text** | Slate-light | `#4a7090` | `hsl(207, 32%, 43%)` | Secondary text |
| **Border** | Soft warm border | `#ddd9cc` | `hsl(45, 20%, 83%)` | Card/input borders (soft, warm) |

**Semantic (status only):** success `hsl(142,71%,45%)` · warning/amber `hsl(38,92%,50%)` ·
error/destructive `hsl(0,84%,60%)` · info `hsl(217,91%,60%)`.

**Ready-to-paste tokens:**

```css
:root {
  --background:  44 35% 94%;   /* warm cream — page bg */
  --card:        45 36% 96%;   /* light cream — card fill */
  --foreground:  209 39% 19%;  /* slate-dark — text */
  --muted-foreground: 207 32% 43%;
  --primary:     206 35% 28%;  /* #2E4A5F slate */
  --primary-foreground: 55 52% 88%;  /* cream text on slate */
  --accent-from: 206 35% 28%;
  --accent-to:   35 65% 47%;   /* amber */
  --border:      45 20% 83%;
  --radius:      0.75rem;      /* 12px */
}
```
Usage: `hsl(var(--background))`, `hsl(var(--primary))`, etc.

---

## 3. Typography

```css
--font-serif: 'Josefin Sans', Georgia, sans-serif;   /* headings / wordmark */
--font-sans:  'Georgia', 'Times New Roman', serif;   /* body text */
--font-mono:  'JetBrains Mono', 'Fira Code', monospace; /* code, JSON, paths */
```

**Import (put in `<head>`):**
```html
<link href="https://fonts.googleapis.com/css2?family=Josefin+Sans:wght@300;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
```

**Rules:**
- **Josefin Sans** — every heading h1–h6, the wordmark (hairline 300 "Hendo" +
  bold 700 "Code"), page/section titles. Uppercase, wide tracking.
- **Georgia (serif)** — all body text.
- **JetBrains Mono** — code blocks, JSON/YAML, file paths, terminal output.

---

## 4. Components (content HTML)

- **Buttons — primary:** slate bg `hsl(206,35%,28%)`, cream text, `border-radius: 0.75rem`.
  **Secondary:** cream bg, slate text, warm border.
- **Cards:** cream fill, soft warm border, radius 12px, padding ~20px. Minimal shadow.
- **Badges/pills:** rounded-full, small. Status uses the semantic colors above.
- **Tables:** uppercase header, horizontal borders only, no vertical borders, no zebra striping.
- **Radius scale:** 12px default · 16px large cards/modals · full for pills.

---

## 5. Rules for generated HTML artifacts

- Use the brand colors above: slate `hsl(206,35%,28%)`, cream `hsl(44,35%,94%)`,
  amber accent `hsl(35,65%,47%)`.
- Josefin Sans for headings, Georgia for body.
- **Inline styles only** — no Tailwind classes, no `<style>` blocks, no `class`
  attributes (keeps the artifact self-contained and portable).
- No lorem ipsum — use real, honest content.

---

## 6. Logo & naming

- **Full logo:** `https://hendocode.com/`
- **Wordmark:** "Hendo" (hairline) + "Code" (bold amber) — the wordmark is text, not an image.
- **Company name:** Hendo Code in copy (see `brand-guidelines.md` for name/formatting rules).
