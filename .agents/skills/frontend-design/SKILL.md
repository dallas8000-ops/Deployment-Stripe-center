---
name: frontend-design
description: >-
  Gives Claude a real design system so UI doesn't come out generic. Applies
  consistent tokens (color, spacing, typography, radius, shadow), component
  patterns, and layout rules when building or modifying any frontend UI. Use
  when building new UI components, pages, or layouts — especially when the
  result needs to look polished rather than plain. Triggers on: "build a UI
  for", "design a component", "make this look good", "style this page", "add
  a dashboard", "create a form", or any frontend visual work.
metadata:
  short-description: Design system and UI tokens for polished frontends

---

## Design principles

1. **Hierarchy over decoration** — size, weight, and whitespace carry meaning. Don't use color as the only differentiator.
2. **Spacing rhythm** — use a 4px base grid. Prefer 4, 8, 12, 16, 24, 32, 48, 64px. Never mix arbitrary values.
3. **One accent color** — the primary action color should appear sparingly. Everything else is neutral.
4. **Accessible by default** — 4.5:1 contrast for body text, 3:1 for large text/UI components, focus rings on all interactive elements.

## Token system (CSS custom properties)

```css
:root {
  /* Color — neutrals */
  --color-bg:        #0f0f0f;
  --color-surface:   #1a1a1a;
  --color-border:    #2e2e2e;
  --color-muted:     #6b6b6b;
  --color-subtle:    #a0a0a0;
  --color-primary-text: #f5f5f5;

  /* Color — accent (swap these for light mode or brand) */
  --color-accent:        #6366f1;   /* indigo-500 */
  --color-accent-hover:  #4f46e5;
  --color-accent-text:   #ffffff;
  --color-success:       #22c55e;
  --color-warning:       #f59e0b;
  --color-error:         #ef4444;

  /* Spacing */
  --space-1: 4px;   --space-2: 8px;   --space-3: 12px;
  --space-4: 16px;  --space-5: 24px;  --space-6: 32px;
  --space-7: 48px;  --space-8: 64px;

  /* Typography */
  --font-sans: "Inter", system-ui, -apple-system, sans-serif;
  --font-mono: "JetBrains Mono", "Fira Code", monospace;
  --text-xs:   11px;  --text-sm: 13px;  --text-base: 15px;
  --text-lg:   17px;  --text-xl: 20px;  --text-2xl:  24px;
  --text-3xl:  30px;  --text-4xl: 36px;
  --weight-normal: 400;  --weight-medium: 500;  --weight-semibold: 600;  --weight-bold: 700;
  --leading-tight: 1.25;  --leading-normal: 1.5;  --leading-relaxed: 1.75;

  /* Radius */
  --radius-sm: 4px;  --radius-md: 8px;  --radius-lg: 12px;  --radius-full: 9999px;

  /* Shadow */
  --shadow-sm:  0 1px 2px rgba(0,0,0,.4);
  --shadow-md:  0 4px 12px rgba(0,0,0,.5);
  --shadow-lg:  0 8px 24px rgba(0,0,0,.6);

  /* Transition */
  --transition-fast: 120ms ease;
  --transition-base: 200ms ease;
}
```

## Component patterns

### Button
```css
.btn {
  display: inline-flex; align-items: center; gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-md);
  font-size: var(--text-sm); font-weight: var(--weight-medium);
  cursor: pointer; border: none; transition: background var(--transition-fast);
}
.btn-primary { background: var(--color-accent); color: var(--color-accent-text); }
.btn-primary:hover { background: var(--color-accent-hover); }
.btn-ghost { background: transparent; color: var(--color-subtle); border: 1px solid var(--color-border); }
.btn-ghost:hover { background: var(--color-surface); color: var(--color-primary-text); }
```

### Card
```css
.card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  box-shadow: var(--shadow-sm);
}
```

### Input / Form field
```css
.input {
  width: 100%; padding: var(--space-2) var(--space-3);
  background: var(--color-bg); border: 1px solid var(--color-border);
  border-radius: var(--radius-md); color: var(--color-primary-text);
  font-size: var(--text-sm); transition: border-color var(--transition-fast);
}
.input:focus { outline: none; border-color: var(--color-accent); box-shadow: 0 0 0 3px rgba(99,102,241,.2); }
```

### Badge / Tag
```css
.badge {
  display: inline-flex; align-items: center;
  padding: 2px var(--space-2);
  border-radius: var(--radius-full);
  font-size: var(--text-xs); font-weight: var(--weight-medium);
  background: rgba(99,102,241,.15); color: var(--color-accent);
}
```

## Layout rules

- **Page max-width**: 1200px, centered with `margin: 0 auto; padding: 0 var(--space-5)`.
- **Sidebar layout**: `display: grid; grid-template-columns: 240px 1fr;`
- **Card grid**: `display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--space-5);`
- **Stack (vertical)**: `display: flex; flex-direction: column; gap: var(--space-4);`
- **Inline cluster**: `display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap;`

## Typography scale in use

| Use | Token | Weight |
|-----|-------|--------|
| Page title | `text-3xl` | semibold |
| Section heading | `text-xl` | semibold |
| Card title | `text-base` | medium |
| Body / description | `text-sm` | normal |
| Caption / meta | `text-xs` | normal, muted color |
| Code | `font-mono`, `text-sm` | normal |

## Rules when building UI

- Always import Inter from Google Fonts or use `system-ui` fallback — never leave font as browser default.
- Every interactive element needs a visible focus state (`:focus-visible`).
- Use `rem` or token variables — never raw `px` in component styles except for tokens themselves.
- Don't use more than 3 font weights on one page.
- Prefer Tailwind utility classes when the project already uses Tailwind; map tokens to the closest Tailwind class.
- When adding icons, use `lucide-react` (if React) or inline SVG — not emoji or Unicode characters.
- Test at 375px, 768px, and 1280px widths before calling a layout done.
