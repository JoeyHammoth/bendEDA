# Documentation site

Static, dependency-free, deployed to GitHub Pages by `.github/workflows/pages.yml`
on every push to `main` that touches `site/`.

**Live:** <https://joeyhammoth.github.io/bendEDA/>

```text
site/
  index.html        one page: problem, ladder, quickstart, CLI reference, metrics, authorship, status
  styles.css        dark theme, tokenised; responsive at 1020px and 640px
  app.js            copy-to-clipboard, CLI table filter, scrollspy — all optional
  assets/icons/     Icons8 PNGs (see provenance below)
```

## Why no static-site generator

The protocol document is the source of truth and it already lives in git as
Markdown. A generator would add a build dependency and a second rendering of the
same facts. The site instead says the small number of things a *user of the CLI*
needs, and links to the repository for everything canonical.

## Local preview

```bash
python -m http.server 8000 --directory site
# then open http://localhost:8000
```

`python tools/check_site.py site` validates that every local `href`/`src`
resolves and that no page still contains a template marker. It runs in CI before
the artifact is uploaded, so a broken link cannot be deployed silently.

## Asset provenance

Icons are from **Icons8** (fluent style), retrieved through the Icons8 MCP server
configured in `.agents/mcp.json` on 2026-11-21, and committed locally so the page
has no runtime third-party dependency and no hotlinking:

| File | Icons8 id | Used for |
|---|---|---|
| `circuit.png` | `TQdcIw079dPL` | brand mark, favicon |
| `integrated-circuit.png` | `rCrXcG8V0lsD` | hero illustration |
| `command-line.png` | `9hLY0P1ixONa` | quickstart |
| `spec-lock.png` | `TkUmhIuENHBp` | spec-lock concept, hero chip |
| `open-book.png` | `39FLspc26r4c` | links, authorship callout |
| `law.png` | `Njg6Q8UV6MHS` | laws concept |
| `pipeline.png` | `hWpn2wTeNAje` | conformance chain |
| `tree.png` | `E43SDB7hSZLx` | plugin surface |
| `ai-chip.png` | `VMAmthbSYf7P` | agentic problem card |
| `check-all.png` | `IJNt9jGwqy9N` | proof-check status |

Icons8's free-use terms require attribution unless a licence is purchased; the
footer credits Icons8, and this table records the exact ids so any asset can be
replaced or re-licensed later. Icons are design furniture here: nothing on the
page depends on an image to be understood.
