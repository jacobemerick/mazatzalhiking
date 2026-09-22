# mazatzalhiking

Route builder for the [Mazatzal Wilderness](https://www.fs.usda.gov/tonto) — stitch
trusted GPS tracks into loops, lassos, figure-eights, and out-and-backs, then export
GPX/KML with waypoints and trail-condition notes.

The route builder exists at `/build/` but is not linked or indexed yet. The trail pages
live at `/trails/`.

## Stack

Hugo renders the site; Cloudflare Workers Builds runs `tools/build.sh` on every push and
deploys `public/` as an assets-only Worker. Nothing generated is committed. The condition
notes are markdown under `content/trails/` — that is the file to open after a hike.

- `wrangler.jsonc` — Worker config (assets-only, no `main` script)
- `hugo.toml`, `layouts/` — the site's templates; `layouts/index.html` and `404.html`
  are the landing and not-found pages verbatim
- `content/trails/<slug>.md` — **the condition notes**, one file per trail
  (`docs/condition-observations.md` has the format); `content/about.md`
- `static/build/` — the route builder (Leaflet, plain JS; see `docs/route-builder.md`)
- `static/js/conditions.js` — the builder's observation renderer;
  `layouts/partials/observations.html` is its twin for the pages, and
  `tools/check_renderers.mjs` fails the build if they disagree
- `static/css/site.css` — shared styles for the content pages
- `static/data/`, `data/`, `public/` — built, never committed
- `archive/` — immutable recorded GPX
- `curation/` — the authored trail graph and observations (`docs/trail-graph-schema.md`,
  `docs/condition-observations.md`)
- `tools/` — curation, geometry, validation and site build tooling

## Writing a condition note

Open `content/trails/<slug>.md`, find the leg's `## … {#id}` section, and add:

```
### 2026-09-21 water
The seep was running again after the monsoon.
```

One sentence per line. Then `./tools/build.sh` to check it parses and see it rendered.

## Data changes

After editing anything under `curation/`:

```bash
./tools/build_geometry.py   # only if segments were drawn or redrawn
./tools/sync_trails.py      # adds a markdown section for any new leg; --fix renames headings
./tools/build.sh            # validate, build data, hugo, check renderers
```

`build.sh` is what Cloudflare runs. Needs Hugo (`brew install hugo`), Python 3 and Node.

## Local development

```bash
npm install
npm run dev      # tools/build.sh, then wrangler dev serving public/ at localhost:8787
hugo server      # or just the pages, with live reload (run build_site.py first for data/)
```

## Deploy

Cloudflare Workers Builds is wired to this repo with build command `tools/build.sh`
and build variable `HUGO_VERSION=0.157.0`; it runs `npx wrangler deploy` on push to
`main`. Every other branch is uploaded as a preview version, and
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

## License

Code (`tools/`, `layouts/`, `static/`, `schema/`, `.github/`, root config): MIT, see
`LICENSE`. The recorded tracks, curated graph, trail notes and trip reports
(`archive/`, `curation/`, `content/`): CC BY-NC-ND 4.0, see `LICENSE-CONTENT` — share
with credit, no commercial use, no derivatives. Contributions: `CONTRIBUTING.md`.
