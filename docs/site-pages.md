# Site pages

Decision record for [#30](https://github.com/jacobemerick/mazatzalhiking/issues/30),
covering the trail list ([#32](https://github.com/jacobemerick/mazatzalhiking/issues/32)),
the trail pages ([#31](https://github.com/jacobemerick/mazatzalhiking/issues/31)) and the
builder deep link ([#34](https://github.com/jacobemerick/mazatzalhiking/issues/34)).
The public surface itself was decided under #20: six page types and nothing else.

Implementation: Hugo, with the layouts under [`layouts/`](../layouts), the authored
pages under [`content/`](../content), and the data the templates read produced by
[`tools/build_site.py`](../tools/build_site.py). The whole build is
[`tools/build.sh`](../tools/build.sh).

## Pages are built on deploy, and the site is written in markdown

**Decision (2026-09-21, superseding the first cut): the pages are Hugo output, built by
Cloudflare Workers Builds on every push. Nothing generated is committed. The condition
notes are authored in markdown, one file per trail, and the JSON the builder reads is
derived from them.**

The first version of #30 did the opposite: a Python generator wrote the HTML and the
output was committed so the diff could be the review. That was the right call while the
notes lived in JSON, and it stopped being right the moment there were notes to review.
Jacob's requirement, stated when the first 246 notes arrived: *"as I visit this
wilderness in the future I only want to edit the markdown."* A condition note is a
sentence written after a walk; the file it lives in has to be one a person opens and
types into, and its diff has to read as prose. Markdown with one sentence per line is
that, JSON is not.

So the authoring layer moved and the build moved with it:

- `content/trails/<slug>.md` is authored. Its `##` sections are the trail's legs, its
  `###` entries are the dated notes, and the text above the first `##` is an optional
  introduction. The format is documented in
  [`condition-observations.md`](condition-observations.md).
- `tools/build_site.py` parses those files into the observation document the schema
  describes, validates it against the graph, and writes it for the builder
  (`static/data/observations.json`) and for the templates (`data/conditions.json`,
  grouped by target and sorted newest first). It also precomputes each trail's legs in
  walking order with figures for that direction (`data/trails.json`), so the templates
  never chain legs or swap gain and loss themselves.
- `hugo` renders. `public/`, `data/` and `static/data/` are gitignored.
- Workers Builds runs `tools/build.sh` as its build command and deploys `public/`. The
  deployed artifact is still an assets-only Worker; the build step exists in Cloudflare's
  pipeline, not in the Worker.

What is given up: the committed-output diff. What replaces it: the markdown diff, which
is the thing that was actually wanted, and a CI build on every pull request so a note
that does not parse is red before it is merged.

**Hugo version:** pinned at the minimum in `hugo.toml` and set explicitly with the
`HUGO_VERSION` build variable in the Workers Builds settings, so Cloudflare builds with
the version the layouts were written against rather than the image default.

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

**Decision: two implementations, one test.** The pages render notes through
[`layouts/partials/observations.html`](../layouts/partials/observations.html), a Go
template written as the twin of `conditions.js`: same elements, classes, wording,
ordering and date format. Hugo cannot call the JavaScript, so the rule is enforced
after the build instead of by construction:
[`tools/check_renderers.mjs`](../tools/check_renderers.mjs) runs the real
`conditions.js` under a DOM just large enough for it, renders every target's notes,
and compares with what Hugo wrote into every built page. A difference in structure,
wording, ordering or date format fails the build. (The first cut ran `conditions.js`
itself at generation time and pasted the result in; that option went away with the
Python generator.)

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
- Per-trail prose is the text above the first `##` in the trail's markdown file. #31
  allows a short introduction; none has been written yet, and the hook costs nothing.

## Not included

- A sitemap entry or landing-page link for the builder (Jacob's gate).
- Trailhead grouping on the trail list. #32 permits it; it is not needed with 49 entries.
- Per-page JSON-LD. Nothing consumes it yet.
