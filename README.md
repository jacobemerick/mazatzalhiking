# mazatzalhiking

Route builder for the [Mazatzal Wilderness](https://www.fs.usda.gov/tonto) — stitch
trusted GPS tracks into loops, lassos, figure-eights, and out-and-backs, then export
GPX/KML with waypoints and trail-condition notes.

Right now this is just the landing page.

## Stack

Static assets served by a Cloudflare Worker. No build step, no framework — `public/`
is deployed as-is.

- `wrangler.jsonc` — Worker config (assets-only, no `main` script)
- `public/index.html` — landing page
- `public/404.html` — not-found page

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

## Roadmap

- [ ] Trail + POI data model, seeded from recorded tracks
- [ ] Route builder UI (pick trailhead → segments → POIs → shape)
- [ ] Graph routing for loop / lasso / figure-eight / out-and-back generation
- [ ] Condition notes per segment, surfaced in the builder and in exports
- [ ] GPX + KML export with named waypoints and descriptions
