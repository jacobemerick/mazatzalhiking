# archive

Raw recorded source data. **Nothing here is served** — the Worker publishes only
`public/` (see `wrangler.jsonc`). These are inputs to a build, never runtime assets.

Treat these files as immutable. Cleaning, smoothing, and merging happen downstream and
write their output elsewhere; the point of this directory is that the original recording
is always recoverable.

## `gpx/` — 25 trips, 599 recorded miles, 2016-03-05 to 2026-05-23

The source of record. Two exporters:

- `NNNNN_Name.gpx` (20 files) — HikeArizona via GPSBabel. The numeric prefix is the
  HikeArizona trip id and is worth keeping. **These carry no trackpoint timestamps.**
- `RS_*.gpx` (5 files) — TrailDEX. Full timestamps at roughly 7-second intervals.

Filenames are as exported, minus the ` (1)` suffix browsers add to repeat downloads.
Trip dates and names are **not** in most of these files; they live in `tools/trips.csv`,
which is the manifest that makes the corpus interpretable.

## `hikearizona-bulk-export.gpx`

HikeArizona's all-trips-in-one-file export, covering 19 of the 25 trips.

**Its geometry is unusable** — decimated to a flat ~38 m regardless of curvature, which
understates distance by 6.9% and straightens switchbacks. Do not ingest it.

It is kept for one reason: **it holds the only surviving copy of trackpoint timestamps
for 11 trips** whose per-trip GPSBabel exports were stripped. Those times interpolate
onto the good geometry by nearest-neighbour (median deviation 7-11 m). Deleting this file
loses them permanently.

## `dem-3dep.json`

Elevation sampled from USGS 3DEP, keyed by `"lon,lat"` to six decimal places, in metres.
Not recorded by anyone here — it is an external reference surface — but it belongs in this
directory for the same reason the tracks do: it is an immutable build input, it is never
served, and regenerating it from scratch costs a long run against a public service.

Every point of the committed network resolves at **1 m lidar** resolution. Committing the
samples is what lets `tools/build_geometry.py` rebuild the whole graph with no network
access; only coordinates that have never been asked for cost a request.

Why the published gain comes from here and not from the recorded altimeter channel:
[`docs/elevation.md`](../docs/elevation.md).

## `haz/` — Jacob's own writing on HikeArizona

Trail guides and trip reports Jacob wrote and published on HikeArizona, pulled by
hand and stored here as text. This is the source of the site's dated condition
observations (#18): the trip reports are where "what I saw, on which day" was recorded
at the time. It is **not** published as-is — #20 decided that any trail prose on the
site is written fresh, so nothing here is copied onto a page.

- `guides/<slug>.md` — one per trail, named by the trail's `slug` in `curation/graph.json`
  (28 of 49 trails have one). HAZ's fixed sections are Markdown headings: `## Overview`,
  `## Warning`, `## History`, `## Hike`, `## Water Sources`, `## Camping`; a guide that
  breaks its Hike into stretches uses `###` for them. Body text is as written. The only
  edits on import were the headings and collapsing the double spaces left behind where
  an inline link carried an icon.
- `triplog/` — trip reports, dated.

---

Findings and full numbers: [`docs/gpx-corpus-inventory.md`](../docs/gpx-corpus-inventory.md).
Regenerate with `./tools/inventory.py archive/gpx`.
