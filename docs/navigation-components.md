# Navigation Components Guide

## Overview
The site now uses client-side navigation components instead of inline per-page headers.
There are three nav profiles:

- `home` (homepage family)
- `gas` (gassensing family)
- `bio` (biosensing family)

Each page mounts a nav component via:

```html
<div id="mc-nav-root" data-nav-profile="home|gas|bio"></div>
<noscript>...fallback links...</noscript>
<script src="/assets/js/nav-loader.js"></script>
```

## File Map

### Component Partials
- `/assets/partials/nav-home.html`
- `/assets/partials/nav-gas.html`
- `/assets/partials/nav-bio.html`

### No-JS Fallback Partials
- `/assets/partials/nav-home-noscript.html`
- `/assets/partials/nav-gas-noscript.html`
- `/assets/partials/nav-bio-noscript.html`

### Loader
- `/assets/js/nav-loader.js`

### Tooling
- Migration: `/tools/migrate_nav_to_component.py`
- Verification: `/tools/verify_nav_component_usage.py`

## Which Pages Use Which Profile
Profiles follow `tools/migrate_nav_to_component.py` mapping:

- `home`: `index.html`, `pages/about/*`, `pages/contact/*`, `pages/news/*`, `pages/careers/*`
- `gas`: `pages/gassensing/*`, `pages/gassensing/cases/*`, `pages/solutions/*`, `pages/measurement/*`, `pages/research/*`, `pages/customization/*`
- `bio`: `pages/biosensing/*`

## Dynamic Data Behavior

`nav-loader.js` handles common interactions and profile-specific data loading.

### `gas` profile dynamic sources
- `/api/products/with-settings` -> fills `dynamic-product-list`
- `/api/recommendations` -> fills `latestReleasesList`, `applicationAreasList`
- `/api/products/industry-filters` -> fills `categoriesLeft`, `categoriesRight`
- `/api/measurement-targets` -> fills `measurementTargetsLeft`, `measurementTargetsRight`

### `bio` profile
- Keeps minimal equivalent behavior (interaction only by default).
- No forced admin mapping added in this migration.

## How To Update Navigation UI
1. Edit the relevant partial file in `/assets/partials/`.
2. Keep links as absolute web paths (`/pages/...`, `/assets/...`).
3. If adding/removing dynamic placeholders, update `nav-loader.js` accordingly.
4. Run verification script.

## Validation Commands

```bash
python3 tools/verify_nav_component_usage.py
```

Optional (re-apply migration template rules):

```bash
python3 tools/migrate_nav_to_component.py
```

## Git Hook Behavior
Pre-commit no longer bulk-rewrites all pages for nav sync.
It now runs verification only:

- hook file: `/.git/hooks/pre-commit`
- verification script: `/tools/verify_nav_component_usage.py`

If verification fails, commit is blocked until pages follow the component contract.

## Common Issues

### 1) Nav not rendering
- Check page has `#mc-nav-root` and valid `data-nav-profile`.
- Check `/assets/js/nav-loader.js` is included.
- Check browser console/network for partial fetch errors.

### 2) Gas menu sections empty
- Confirm placeholders exist in `nav-gas.html` (`dynamic-product-list`, `categoriesLeft/Right`, `measurementTargetsLeft/Right`, etc.).
- Confirm APIs return data.

### 3) Links broken on deep pages
- Use absolute web paths in partials (`/pages/...`) to avoid depth issues.

### 4) No-JS scenario
- Fallback content comes from `*-noscript.html` partial content injected into pages during migration.
- Update fallback links in `/assets/partials/nav-*-noscript.html` and rerun migration if you want to refresh existing pages.

## Notes
- `tools/sync_nav.py` is retained for reference/backward compatibility but is no longer the primary workflow.
- Primary workflow is now: edit partials + verify.
