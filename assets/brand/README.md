# Brand assets

This directory holds the official **FnixAgent** brand assets (logo, wordmark, color palette, OG image, etc.).

> 📌 **TL;DR:** Use the wordmark for headers, the icon for app tiles, the OG image for social previews. Don't recolor, skew, or remix without permission.

---

## Files in this directory

| File | Format | Size | Use |
|------|--------|------|-----|
| `logo.svg` | SVG | vector | Primary logo (icon + wordmark, light theme) |
| `logo-dark.svg` | SVG | vector | Primary logo, dark theme |
| `logo-mono.svg` | SVG | vector | Monochrome, single-color print |
| `icon.svg` | SVG | vector | Square app icon |
| `icon-512.png` | PNG | 512×512 | Tauri bundler / desktop icon |
| `icon-256.png` | PNG | 256×256 | GitHub social card (small) |
| `wordmark.svg` | SVG | vector | "FnixAgent" text only |
| `og-image.png` | PNG | 1280×640 | Social preview (GitHub, Twitter, etc.) |
| `favicon.ico` | ICO | multi | Browser tab |
| `colors.md` | — | — | Brand color palette (token names + hex) |
| `typography.md` | — | — | Brand typography |
| `usage.md` | — | — | When to use which asset, what not to do |

---

## Where these are used

- `apps/workbench/src-tauri/icons/` — generated from `icon-512.png` and friends (Tauri).
- `docs/` — embeds `logo.svg` in the docs index.
- `README.md` — references `og-image.png` for the GitHub social preview.
- Twitter / blog posts — `og-image.png`.

---

## Don't

- ❌ Don't recolor the logo.
- ❌ Don't put the logo on a busy background.
- ❌ Don't use the icon for anything other than app tiles / favicons.
- ❌ Don't generate derivatives without a written OK from the lead maintainer.
- ❌ Don't use the wordmark "Fnix" alone to refer to other projects (it can be confused with Phoenix, Finix, etc.).

---

## License

All brand assets in this directory are © FnixAgent. The wordmark and logo may be used to **refer to** the project (e.g., in articles, talks, screenshots) under fair use. Commercial use of the marks requires written permission — see `usage.md`.

See [../LICENSE](../LICENSE) for the project license (which does **not** grant trademark rights).
