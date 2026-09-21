# Site pages

Decision record for [#30](https://github.com/jacobemerick/mazatzalhiking/issues/30),
covering the trail list ([#32](https://github.com/jacobemerick/mazatzalhiking/issues/32)),
the trail pages ([#31](https://github.com/jacobemerick/mazatzalhiking/issues/31)) and the
builder deep link ([#34](https://github.com/jacobemerick/mazatzalhiking/issues/34)).
Implementation in [`tools/build_pages.py`](../tools/build_pages.py). The public surface
itself was decided under #20: six page types and nothing else.

## Generated output is committed

**Decision: `tools/build_pages.py` writes `public/trails/` and `public/sitemap.xml`, and
the result is committed, not built on push.**

The ticket left this open between committing the HTML and building it in Workers
Builds. Committing wins for the same reasons `public/data/` is committed:

- The deployed artifact stays an assets-only Worker with no build step. `wrangler
  deploy` ships what is in the repo; there is nothing that can succeed locally and fail
  in CI.
- The diff is the review. A change to the graph shows up as a change to the pages it
  affects, and a change to the template shows up on every page, which is exactly the
  blast radius a reviewer wants to see.
- `--check` mode makes drift detectable: it regenerates in memory, compares, and exits
  non-zero if the committed output is stale. That belongs in a pre-push check.

The cost is 50 generated files in the repo. They are small and they change only when
the data does.

## URLs

**Decision: `/trails/<slug>/`, with `slug` an authored field on the trail.**

The ticket says slugs come from trail names and must be stable, and those two
requirements conflict the moment a trail is renamed: a derived slug follows the name
and moves the page. So the slug is *assigned from* the name once and stored in
`graph.json` beside it, and the generator never recomputes it. A rename changes the
heading and leaves the URL alone. The validator requires every trail to have one and
refuses duplicates.

Slugs are the full name, lower-cased, non-alphanumerics collapsed to hyphens:
`barnhardt-trail`, `fr-201`, `willow-springs-spur`. The word "trail" is kept because
dropping it makes `willow-springs-trail` and `willow-springs-spur` fight over
`willow-springs`.

The trail list is `/trails/`. The about page is `/about/`, hand-written.

## Leg order on a trail page

A trail's legs are chained by their shared nodes into one path. Where to start reading
the path is a choice, and it is made the same way every time: at the trailhead when
exactly one end of the trail is one, otherwise at the lower end, since trails are
conventionally described from the bottom up. A leg walked against its recorded
direction has its gain and loss swapped on the page, so the figures describe the
direction the page reads in, and the same orientation is what the builder deep link
encodes.

One trail is not a simple path: Saddle Mountain Trail includes the Mine Loop, a leg
that starts and ends at the same node. Self-loops are listed immediately after the leg
that arrives at their node. Any other non-path shape is reported as a warning and
listed in file order, so a future curation change cannot silently produce a page in
the wrong order.

## One renderer for observations

[#19](https://github.com/jacobemerick/mazatzalhiking/issues/19) requires that every
surface render condition observations through one component, so that the builder and
the pages cannot show them differently. The generator is Python and the component is
`public/js/conditions.js`; the obvious move is a Python port, and a port is a second
implementation that will drift.

**Decision: the generator runs the real `conditions.js` under Node.**
[`tools/render_conditions.mjs`](../tools/render_conditions.mjs) provides a DOM just
large enough for it — five members — and serialises what it builds. The rules the
component enforces (newest first, date always visible, the empty state says nothing is
recorded rather than implying the trail is clear, blank lines are the only markup) hold
on the pages because it is the same code. Node is already a dependency of the repo
through wrangler.

## The builder deep link

Every trail page carries a link to `/build/?r=<legs>`, the legs in page order with
direction flags. The builder infers direction when flags are absent, but the page
knows the direction it is describing, so it says so. This closes #34.

The builder is still unlinked from the landing page and carries `noindex`; that gate is
Jacob's and is unchanged by this. The trail pages link to it because that link is the
point of the pages.

## What the pages say, and what they do not

- Distance and elevation come from the leg's recorded line and the DEM, never typed in.
- The recorded date of the source track is shown, because the walked-it-myself
  provenance is the argument for trusting the page.
- A leg with no observation shows the component's empty state. Nothing is invented to
  fill it.
- There is no per-trail prose. #31 allows a short written introduction; none exists
  yet, and the generator has no hook for one until there is something to hook in.

## Not included

- A sitemap entry or landing-page link for the builder (Jacob's gate).
- Trailhead grouping on the trail list. #32 permits it; it is not needed with 49 entries.
- Per-page JSON-LD. Nothing consumes it yet.
