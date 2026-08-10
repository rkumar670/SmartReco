---
name: build-learning-marketplace-ui
description: Design and implement polished responsive learning marketplaces, course catalogs, recommendation dashboards, career-learning portals, and similar content-heavy SaaS interfaces. Use when Codex needs to create or restyle web UI with sticky navigation, search, card grids, horizontal recommendation shelves, filter sidebars, course detail pages, design tokens, dark mode, and accessible responsive behavior. Adapt the visual identity to the target product instead of copying SmartReco branding.
---

# Build Learning Marketplace UI

Build a calm, content-first marketplace that makes browsing and resuming learning easy. Preserve the target project's framework, conventions, and component system.

## Workflow

1. Inspect the existing app, routes, components, CSS, and design dependencies before editing.
2. Identify the primary journeys: discover, filter, inspect, enroll, resume, and track progress.
3. Define a small token layer before styling individual components. Read [references/design-system.md](references/design-system.md).
4. Establish the page shell: constrained content width, sticky header, search, primary navigation, and optional category rail.
5. Build reusable content patterns only where at least two real screens need them: cards, shelves, chips, progress rows, detail sidebars, and filter groups.
6. Implement responsive behavior with CSS Grid and Flexbox. Prefer intrinsic layouts such as `auto-fill`, `minmax()`, wrapping, and horizontal overflow over breakpoint-heavy duplication.
7. Verify keyboard focus, semantic landmarks, contrast, reduced motion, overflow, empty states, and both narrow and wide layouts.
8. Run the project's normal formatter, lint, tests, and visual checks.

## Layout rules

- Use a centered shell around 68-72rem wide with 1-1.5rem inline padding.
- Keep global navigation sticky when persistent search or navigation materially helps browsing.
- Use responsive card grids: `repeat(auto-fill, minmax(16rem, 1fr))` is a starting point, not a mandate.
- Use horizontal shelves for ranked or personalized recommendations; use grids for catalogs.
- Use a two-column detail layout with flexible content and a 18-20rem supporting sidebar. Collapse it to one column before either side becomes cramped.
- Use a 14-16rem sticky facet sidebar for large catalogs. Collapse filters into the content flow or a disclosure on small screens.
- Keep mobile category navigation on one horizontally scrollable row instead of allowing it to consume several rows.
- Render sections only when they contain useful content. Treat headings as promises.

## Visual rules

- Use neutral surfaces, one clear accent family, restrained gradients, subtle borders, rounded cards, and a small elevation scale.
- Keep typography compact and readable. Use a limited type scale and slightly tightened display headings.
- Prefer system fonts unless the target brand already supplies typography.
- Give cards consistent media ratios and content rhythm. Align actions or metadata at the bottom when cards share a row.
- Use chips for compact filters and tags, not for ordinary navigation or every piece of metadata.
- Use motion only to clarify interaction. Respect `prefers-reduced-motion`.
- Support dark mode only when it can be applied coherently through tokens; do not scatter one-off overrides.

## Adaptation rules

- Preserve the layout logic, not the source project's name, copy, icons, exact colors, or domain data.
- Derive accent colors, radius, density, and imagery from the target product's audience and brand.
- Do not add Tailwind, Bootstrap, Material UI, or another framework when the project already has a workable styling approach.
- Do not make every screen card-based. Use plain lists or rows for dense progress and administration views.
- Do not introduce a component abstraction for a single occurrence.
- Do not hide essential actions behind hover-only interactions.

## Completion checklist

- Test approximately 360px, 768px, and a wide desktop viewport.
- Confirm header, shelves, tables, filters, and long titles do not overflow.
- Confirm every interactive element is reachable and visibly focused by keyboard.
- Confirm loading, empty, error, and populated states retain stable structure.
- Confirm color is not the only indicator of state.
- Confirm the result looks native to the target project rather than like a copied template.
