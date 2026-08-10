# Design system reference

Use these values as coherent starting points. Adapt them to the target brand.

## Tokens

```css
:root {
  --bg: #fbfbfd;
  --surface: #ffffff;
  --surface-2: #f4f4f7;
  --border: #e4e4ec;
  --text: #16161d;
  --muted: #6c6c7d;
  --accent: #4f46e5;
  --accent-2: #7c3aed;
  --accent-soft: #eef2ff;
  --good: #0f9d58;
  --warn: #b45309;
  --bad: #c02626;
  --radius: 0.75rem;
  --shadow-xs: 0 1px 2px rgb(20 20 40 / 4%);
  --shadow-sm: 0 2px 6px rgb(20 20 40 / 6%), 0 1px 2px rgb(20 20 40 / 5%);
  --shadow-md: 0 8px 24px rgb(20 20 40 / 8%), 0 2px 6px rgb(20 20 40 / 5%);
  --ease: cubic-bezier(.2, .7, .3, 1);
}
```

Use a compact type scale near `.78rem`, `.85rem`, `.9rem`, `.95rem`, `1.05rem`, `1.15rem`, `1.3rem`, `1.5rem`, and `1.75rem`. Add a step only when the existing scale cannot express a real hierarchy.

## Core patterns

```css
.shell { width: min(100% - 2.5rem, 70rem); margin-inline: auto; }

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr));
  gap: 1rem;
}

.detail-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 19rem;
  gap: 2rem;
  align-items: start;
}

.catalog-layout {
  display: grid;
  grid-template-columns: 15rem minmax(0, 1fr);
  gap: 1.625rem;
  align-items: start;
}

.shelf-track {
  display: flex;
  gap: 1rem;
  overflow-x: auto;
  scroll-snap-type: x proximity;
}

.shelf-track > * { flex: 0 0 min(18rem, 82vw); scroll-snap-align: start; }

@media (max-width: 48rem) {
  .detail-layout, .catalog-layout { grid-template-columns: 1fr; }
}
```

## Component intent

- Header: brand, prominent search, primary destinations, and account/action group.
- Category rail: secondary taxonomy navigation with active state and horizontal overflow.
- Catalog card: consistent media ratio, title, concise description, metadata, and one clear destination.
- Shelf: ranked or personalized content where order matters.
- Filter sidebar: sticky only when viewport height and content make it useful.
- Detail sidebar: enrollment, price, progress, or next action; avoid duplicating the main content.
- Progress row: prefer a dense row over a large card for repeated learning items.

## Accessibility and states

- Use `header`, `nav`, `main`, `section`, `article`, and `footer` landmarks appropriately.
- Label search and icon-only controls. Keep hit targets comfortably usable.
- Apply a consistent `:focus-visible` outline with sufficient contrast.
- Prefer content skeletons that preserve dimensions; avoid layout shifts.
- Disable transforms and nonessential transitions for reduced motion.
- Make active and status states distinguishable by text, shape, or icon as well as color.
