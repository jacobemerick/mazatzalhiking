# mazatzalhiking

Route builder for the [Mazatzal Wilderness](https://www.fs.usda.gov/tonto) — stitch
trusted GPS tracks into loops, lassos, figure-eights, and out-and-backs, then export
GPX/KML with waypoints and trail-condition notes.

The route builder is live at [`/build/`](https://mazatzalhiking.com/build/). Public
trail pages and condition observations are in progress.

## Stack

Static assets served by a Cloudflare Worker. No build step in the deploy, no framework —
`public/` is deployed as-is. Data under `public/data/` is generated locally by
`tools/build_site.py` and committed.

- `wrangler.jsonc` — Worker config (assets-only, no `main` script)
- `public/index.html` — landing page
- `public/build/` — the route builder (Leaflet, plain JS; see `docs/route-builder.md`)
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
```

`build_site.py` refuses to write if the graph fails validation.

## Local development

```bash
npm install
npm run dev      # wrangler dev — serves public/ at localhost:8787
```

## Deploy

Cloudflare Workers Builds is wired to this repo and runs `npx wrangler deploy` on
push to `main`. To deploy by hand:

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
