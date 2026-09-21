# mazatzalhiking

Route builder for the [Mazatzal Wilderness](https://www.fs.usda.gov/tonto) — stitch
trusted GPS tracks into loops, lassos, figure-eights, and out-and-backs, then export
GPX/KML with waypoints and trail-condition notes.

The route builder exists at `/build/` but is not linked or indexed yet: no condition
observations have been written. The trail pages are generated and live at `/trails/`.

## Stack

Static assets served by a Cloudflare Worker. No build step in the deploy, no framework —
`public/` is deployed as-is. Data under `public/data/` and the pages under
`public/trails/` are generated locally and committed.

- `wrangler.jsonc` — Worker config (assets-only, no `main` script)
- `public/index.html` — landing page
- `public/build/` — the route builder (Leaflet, plain JS; see `docs/route-builder.md`)
- `public/trails/` — generated trail list and trail pages (see `docs/site-pages.md`)
- `public/about/` — hand-written about page
- `public/css/site.css` — shared styles for the content pages
- `public/js/conditions.js` — the one renderer for condition observations
- `public/data/` — graph, display lines, per-segment geometry, observations
- `public/404.html` — not-found page
- `archive/` — immutable recorded GPX
- `curation/` — the authored trail graph and observations (`docs/trail-graph-schema.md`,
  `docs/condition-observations.md`)
- `tools/` — curation, geometry, validation and site build tooling

## Data changes

After editing anything under `curation/`:

```bash
./tools/build_geometry.py   # only if segments were drawn or redrawn
./tools/build_site.py       # validates, then rewrites public/data/
./tools/build_pages.py      # validates, then rewrites public/trails/ and sitemap.xml
```

Both build tools refuse to write if the graph fails validation, and both take
`--check` to report drift without writing. `build_pages.py` needs Node (it runs
`public/js/conditions.js` to render observations).

## Local development

```bash
npm install
npm run dev      # wrangler dev — serves public/ at localhost:8787
```

## Deploy

Cloudflare Workers Builds is wired to this repo and runs `npx wrangler deploy` on
push to `main`. Every other branch is uploaded as a preview version, and
`.github/workflows/preview-url.yml` comments its URL on the pull request. For a
stable per-branch URL as well, the dashboard's *non-production branch deploy
command* is:

```
npx wrangler versions upload --preview-alias "$(printf '%s' "$WORKERS_CI_BRANCH" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//; s/^([^a-z])/b-\1/' | cut -c1-40)"
```

which serves the branch at `<alias>-mazatzalhiking.jpemeric.workers.dev`. The
workflow derives the alias the same way and includes it once it answers.

To deploy by hand:

```bash
npm run deploy
```

## Analytics

Cloudflare Web Analytics (cookieless, no personal data). The beacon is embedded in
`public/index.html` and `public/404.html`. The site token in those files is a public
identifier, not a secret — it ships in the page source by design.

Stats live in the Cloudflare dashboard under **Analytics & Logs → Web Analytics**.

Note: because the zone is proxied through Cloudflare, **automatic setup** could inject
the beacon instead, with no code at all. Don't enable both — the beacon would load
twice and double-count.

## Roadmap

Tracked as GitHub milestones. Done: the trail graph from recorded tracks, the condition
observation schema, the route builder with GPX/KML export. Next: authoring condition
observations, public trail pages, builder conveniences (out-and-back mirror, lasso
close, elevation profile).
