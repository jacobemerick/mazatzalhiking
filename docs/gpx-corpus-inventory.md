# GPX corpus inventory

Closes [#4](https://github.com/jacobemerick/mazatzalhiking/issues/4). Sizes the reconciliation
work in M2.

Source of record: [`archive/gpx/`](../archive/gpx) (25 files, 5.2 MB), checked in
alongside this document. That settles the raw-GPX half of
[#8](https://github.com/jacobemerick/mazatzalhiking/issues/8); where full-resolution photos
live is still open there.

Regenerate every number here with:

```
./tools/inventory.py archive/gpx
```

Trip dates and names live in `tools/trips.csv`, because 20 of the 25 files carry neither.

---

## What exists

**25 trips, 29 tracks, 54,962 points, 599.0 recorded miles, 2016-03-05 to 2026-05-23.**

Two export paths, and the difference matters:

| Source | Files | Timestamps | Geometry |
|---|---|---|---|
| HikeArizona, via GPSBabel (`NNNNN_Name.gpx`) | 20 | **none** | good, 2 exceptions below |
| TrailDEX (`RS_*.gpx`) | 5 | full, ~7 s | good |

Resolution is shape-aware — points concentrate where the trail bends, which is what
keeps switchbacks intact:

| curvature | median spacing |
|---|---|
| straight (<10°) | 22.9 m |
| gentle (10–30°) | 15.2 m |
| curvy (30–60°) | 10.7 m |
| hairpin (>60°) | 7.3 m |

Corpus median 12.8 m, p10 5.0 m.

For comparison, HikeArizona's bulk "Mazatzal Project" export (all 19 trips in one file)
is decimated at a flat ~38 m regardless of curvature and **understates distance by 6.9%**
— 502.4 mi against 537.0 mi over the same 19 trips, worst case 10.4%. Do not use it for
geometry. It is still needed for timestamps; see below.

## Mileage: distinct vs repeat

**~317 miles distinct**, at a 25 m tolerance — so **47% of recorded mileage is repeat
ground.** (At a 50 m tolerance it reads 197 mi / 67% repeat, but 50 m starts merging
genuinely parallel trails, so 25 m is the defensible figure.)

That ~317 mi is the sanity target for the network-mileage check in
[#16](https://github.com/jacobemerick/mazatzalhiking/issues/16).

New ground contributed by each trip, chronologically — the tail is where the corpus
saturates:

| Date | Trip | New | Recorded | |
|---|---|---:|---:|---:|
| 2016-03-05 | Club Cabin | 15.3 | 27.0 | 57% |
| 2016-04-02 | Mazatzal Peak Loop | 16.5 | 25.9 | 64% |
| 2016-07-08 | South Fork – Gold Ridge Loop | 9.3 | 13.4 | 69% |
| 2016-09-23 | Rock Creek Park | 11.9 | 27.1 | 44% |
| 2017-03-26 | City Creek Loop | 12.3 | 18.3 | 67% |
| 2017-04-14 | Copper Camp Loop | 28.0 | 33.6 | 83% |
| 2017-05-06 | Mazatzal Peak Super Loop | 7.5 | 21.1 | 36% |
| 2017-05-21 | Deer Creek Loop | 20.6 | 31.1 | 66% |
| 2017-06-12 | S Mazatzal Roundup | 24.1 | 35.4 | 68% |
| 2017-06-24 | Verde River / Deadman Mesa | 22.7 | 27.8 | 81% |
| 2017-09-01 | Club Cabin | 19.0 | 35.3 | 54% |
| 2017-11-05 | Verde River / Red Creek | 22.2 | 28.5 | 78% |
| 2017-11-17 | Sheep Creek Cabin | 12.1 | 29.6 | 41% |
| 2017-12-29 | Fuller Seep Loop | 15.8 | 30.6 | 52% |
| 2018-02-11 | Fig Trail and a Kayak | 9.7 | 14.5 | 67% |
| 2018-06-03 | Barnhardt – Sandy Saddle Loop | 1.9 | 16.8 | 11% |
| 2018-09-03 | Midnight Mesa Loop | 20.2 | 35.7 | 57% |
| 2018-11-11 | Red Crk / Wet Btm / Highwater / Verde | 10.2 | 26.5 | 39% |
| 2018-12-05 | Upper Mazatzal Loop | 24.6 | 51.6 | 48% |
| 2019-06-09 | Sheep Bridge / Mountain Spring Loop | 7.6 | 24.0 | 32% |
| 2020-03-21 | North Fork Falls of Deadman Canyon | 2.2 | 21.0 | 11% |
| 2020-04-12 | Little Saddle Mountain Loop | 0.7 | 3.2 | 21% |
| 2021-02-27 | Black Ridge Loop | 1.8 | 7.5 | 25% |
| 2022-05-12 | Mount Peeley Summit | 0.6 | 5.0 | 13% |
| 2026-05-23 | Sandy Saddle TM 12 | 0.0 | 8.5 | 1% |

## How bad the duplication is

Bad enough that [#13](https://github.com/jacobemerick/mazatzalhiking/issues/13) needs real
tooling, not a manual pass. Every trip but Fig Trail overlaps another.

Heaviest shared-ground pairs:

| Miles | Pair |
|---:|---|
| 33.7 | Midnight Mesa Loop ↔ Sheep Bridge / Mountain Spring Loop |
| 28.8 | Club Cabin 2016-03 ↔ Club Cabin 2017-09 |
| 28.6 | Mazatzal Peak Loop ↔ Mazatzal Peak Super Loop |
| 26.5 | Barnhardt – Sandy Saddle ↔ Mazatzal Peak Loop |
| 19.9 | Upper Mazatzal Loop ↔ Verde River / Deadman Mesa |

**Repeat traversals sit close together: median 5.8 m apart, 90% within 20 m, 95% within
30 m.** So a 20–30 m merge tolerance is right for #13, and averaging across traversals is
viable — these are not wildly divergent lines needing a best-of pick.

The two worst-separated pairs both involve the decimated `37747` Club Cabin file (median
17 m separation against ~5 m elsewhere). That spread is a resolution artifact of that one
file, not real GPS divergence.

## Trail-level coverage and gaps

**Not answerable from this corpus alone.** Tracks record trips, not trails; nothing in the
files names a Forest Service trail. Mapping recorded ground onto named trails — and so
identifying which trails have no coverage — is the junction-and-segment curation in
[#14](https://github.com/jacobemerick/mazatzalhiking/issues/14) and
[#15](https://github.com/jacobemerick/mazatzalhiking/issues/15), and it needs a reference list
of trails in the wilderness to check against. Flagged as a gap this ticket cannot close.

What is known: ~317 distinct miles walked, and the saturation curve above shows the last
six trips added under 8 miles of new ground between them, which suggests the network is
close to fully covered rather than sparsely sampled.

## Known defects

| Trip | Problem | Disposition |
|---|---|---|
| Copper Camp Loop | still decimated, 41.7 m median | no better source exists — accept |
| Club Cabin 2017-09 (`37747`) | still decimated, 46.4 m median; fewer points than the bulk export and 0.1% shorter | no better source exists — accept |
| Rock Creek Park (`33886`) | 5 tracks in one file | **one outing over one night**; ingest must not assume one track per file |
| North Fork Falls of Deadman | track named `Track #1` | real name is in the filename and `<name>` metadata |
| 20 HikeArizona trips | no trackpoint timestamps | 11 recoverable, see below |
| 4 trips | 6 position gaps >250 m (max 327 m) | signal loss under canopy or in canyon; leave for #11 |

### Timestamps

Stripped by the GPSBabel export path, **not** by the 2016–2019 device change — 2016 and
2018 trips are affected alike, and the split falls exactly on the exporter.

HikeArizona still holds the times. Its bulk export retained them for **11 of the 20**
untimed trips, and that decimated line hugs this geometry closely (median deviation
7–11 m, worst 54 m), so per-point times interpolate onto the good geometry by
nearest-neighbour.

- 5 trips timestamped in the source files
- 11 recoverable from the bulk export — **kept as
  [`archive/hikearizona-bulk-export.gpx`](../archive/hikearizona-bulk-export.gpx),
  the only copy of those timestamps**
- **9 trips have no time source at all**

Consequences: [#10](https://github.com/jacobemerick/mazatzalhiking/issues/10) must accept
untimed tracks, and EXIF-time photo placement
([#5](https://github.com/jacobemerick/mazatzalhiking/issues/5)) is impossible for those 9
trips regardless of what the photo library holds.

## Elevation

Recorded range 533–2,182 m (1,749–7,159 ft), consistent with the Verde River up to the
Mazatzal crest. Threshold choice dominates the gain figure, which is what
[#12](https://github.com/jacobemerick/mazatzalhiking/issues/12) has to settle:

| Method | Corpus gain |
|---|---:|
| naive summation | 165,604 ft |
| 3 m threshold | 151,588 ft |
| 5 m threshold | 141,955 ft |
| 10 m threshold | 126,585 ft |

A 39,019 ft spread across threshold choice alone, on numbers that end up on public pages.

## Fire history

Two fires shape trail conditions across this ground:

- **Willow Fire, 2004** — Mount Peeley to the East Verde River; only a small portion along
  the Wet Bottom Trail escaped.
- **Sunflower Fire, 2012** — the southern half, Mount Peeley down to AZ-87.

Both predate the entire corpus, so **every recorded track is post-fire** and there is no
pre/post-fire split in the data. Recency still matters inside the burn scars, where brush
regrowth and deadfall keep changing — relevant to
[#17](https://github.com/jacobemerick/mazatzalhiking/issues/17)'s requirement that an
observation date always travels with the text.

(The 2020 Bush Fire burned the Four Peaks area on the far side of AZ-87 and affected none
of this ground.)
