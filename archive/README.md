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

---

Findings and full numbers: [`docs/gpx-corpus-inventory.md`](../docs/gpx-corpus-inventory.md).
Regenerate with `./tools/inventory.py archive/gpx`.
