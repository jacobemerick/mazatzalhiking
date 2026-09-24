# Route builder

Decision record for [#21](https://github.com/jacobemerick/mazatzalhiking/issues/21).
Lives at [`/build/`](https://mazatzalhiking.com/build/); code in
[`public/build/`](../public/build), data emitted by
[`tools/build_site.py`](../tools/build_site.py).

**Decision: a route is an ordered list of legs, each a segment walked in one direction,
and the only rule is that a leg starts where the previous one ended. The builder does no
pathfinding. It shows the network, lets you click the legs that connect, keeps a running
total, and writes the route out as GPX or KML. Condition notes stay on the trail pages.**

---

## What v1 does

- Draws every segment in the graph on a USGS topo basemap, with junctions and trailheads
- Highlights in gold the segments that can be clicked next; clicking one appends it
- Shows the legs in order with distance, gain and loss for the direction walked, and
  the date the ground was recorded; each leg's trail name links to its trail page
- Undo, clear, copy link
- Downloads a GPX or a KML of the assembled route
- Loads a route from the URL, and writes every change back to it

Nothing else. No route-shape picker, no out-and-back mirror, no lasso close, no
elevation profile, no split-here. Those are [#22](https://github.com/jacobemerick/mazatzalhiking/issues/22),
and the data model already supports them.

## Decisions

### 1. Connectivity is the only rule

The candidate set is computed the same way every time: with an empty route, any segment;
with two or more legs, anything touching the end of the last leg. The leg just walked is
always a candidate, because clicking it again is how an out-and-back gets built, and
walking the same tread twice is a real thing hikers do.

**With exactly one leg, both of its ends are open.** A single clicked segment has no
direction yet; the second click decides it. If the second segment touches the first
leg's `to` node the route runs that way, otherwise the first leg flips. Committing to a
direction on the first click would force the user to think about which end they meant
before there is anything to compare it with.

A click on a segment that is not a candidate does not silently do nothing. It opens the
segment's details, says plainly that it does not connect, and offers to start a new
route there.

### 2. The route lives in the URL, and the encoding is explicit

```
/build/?r=00.04.-04.-00
```

Dot-separated leg ids in walking order. A leading `-` means the segment is walked from
its `to` node to its `from` node. Ids are base62 and the two separators are URL
unreserved characters, so the string never needs encoding. A 15-leg route is about 50
characters.

The graph document expected "start node plus segment list, direction from
connectivity". The flag is there instead for one case: a segment whose two ends are the
same node ([`1P`](../curation/graph.json), the Saddle Mountain Mine Loop) has no
direction that connectivity can recover. Every other case would work either way, and
the flag costs one character per reversed leg.

**Flags are optional on input.** `?r=04.00` infers both directions from how the legs
connect, flipping the first leg if that is what makes them meet. This is so the trail
pages ([#34](https://github.com/jacobemerick/mazatzalhiking/issues/34)) can link to the
builder with nothing but a trail's leg ids in order. Flags are always written on output.

**A stale link degrades, it does not break.** Decoding stops at the first leg that
cannot follow the one before it, keeps everything up to that point, and says why. When
the missing id is a retired segment the message names the halves it was split into and
the date, straight from the tombstone in the graph. That is what the tombstones were
for.

**Shared links are pinned.** [`tools/fixtures/shared-routes.txt`](../tools/fixtures/shared-routes.txt)
lists links that must keep loading: loops, a lasso through `1P` walked backwards, an
out-and-back, every trail page's link as of 2026-09-24, and one link through the
retired `05`. `tools/check_routes.mjs` decodes each one with the builder in every pull
request ([#53](https://github.com/jacobemerick/mazatzalhiking/issues/53)). A curation
change that breaks a line should retire the segment, not edit the line.

The URL is rewritten with `replaceState` on every change, so the address bar is always
a shareable copy of the current route and the back button is not filled with every
click.

### 3. What the client downloads

Three tiers, as the graph document planned, now real:

| file | size | loaded |
|---|---|---|
| `data/graph.json` | 52 KB | on open |
| `data/display.json` | 160 KB | on open |
| `data/geometry/<id>.json` | 2 to 20 KB each | per leg, at export |

`display.json` is every segment simplified to about 9 m, which is below the width of a
drawn line at every zoom the map uses: 15,035 points become 7,346. The full line, with
elevation, is fetched only for the legs in the route and only when writing a file. A
twelve-leg route fetches twelve small files.

Everything under `public/data/` is written by `tools/build_site.py` and is committed.
There is still no build step in the deploy; the Worker stays assets-only. Running the
tool is part of landing a data change, the same way `build_geometry.py` is. Whether the
generated pages of [#30](https://github.com/jacobemerick/mazatzalhiking/issues/30) follow
the same pattern is that ticket's call, but this is the precedent.

The tool refuses to write if `validate_graph.py` reports an error, and adds the checks
only the geometry can answer: every segment's line exists, has points, has a monotone
`cum_m` from zero, and measures the mileage the graph claims for it. That closes the gap
recorded on [#16](https://github.com/jacobemerick/mazatzalhiking/issues/16).

### 4. Basemap: USGS topo from The National Map

Public domain, no key, no usage tier, served as tiles by USGS, and it is the map a hiker
in this range already has in their head: contour lines, spring names, the wilderness
boundary. OpenStreetMap-derived topo layers were the alternative and carry either a
tile-usage policy that a public site should not lean on or attribution terms that would
need care. Nothing about the builder depends on the basemap; swapping the tile URL is
one line.

### 5. Leaflet, no framework, no build

Leaflet 1.9 from cdnjs with subresource integrity, loaded as a plain script. The app is
one file of plain JavaScript with no module system, matching the rest of `public/`. A
framework would buy nothing here: the state is one array, the DOM is one list.

Every segment is drawn twice: a visible line, and above it an invisible line 18 px wide
that takes the clicks and the hover. A 2.5 px line is not a click target on a phone.

### 6. Notes live on the trail pages, and the files are just the route

*Revised 2026-09-24.* v1 put every condition note in the leg list, the popups, the
hover tip and both downloads: in the track description, on a waypoint at every
junction, and on a "Conditions: …" waypoint at the middle of each leg. With the notes
from [#18](https://github.com/jacobemerick/mazatzalhiking/issues/18) in place that was
overwhelming in the popups and the leg list. Jacob's call: keep the builder simple, and
send anyone who wants the conditions to the trail pages.

So the builder shows no notes. Each leg's trail name links to its trail page, where the
notes are dated and in context. The builder's copy of the notes
(`observations.json`) and its renderer (`conditions.js`) were removed with it.

The files are the route and nothing else. A GPX has one `<trk>` per leg, named for the
leg as walked ("Barnhardt Trail: Barnhardt Trailhead to Sandy Saddle / Barnhardt Trail
Junction"), with every point and its DEM elevation. A KML has one `LineString`
placemark per leg, with the same names. There are no waypoints and no descriptions.
The file's name and the builder URL it came from are in the GPX metadata.

### 7. Names, not ids, everywhere a person reads

A leg is shown as its trail name and the two junctions it runs between, in the
direction walked, not as the segment's stored name. Segment names are generated
`from → to`, and read backwards when the leg is walked backwards. Node names are the
same in either direction. Concurrent trails are joined with a slash, so the Divide Trail
where it carries the Arizona Trail reads "Mazatzal Divide Trail / Arizona Trail".

The route name in the file is derived the same way: "A to B", "Loop from A" when the
route returns to its start, or "Out and back from A" when the second half mirrors the
first.

## What v1 does not do, and why not yet

- **No trail names on the map.** Hover shows a segment's name; the map itself carries
  only lines and junction dots. Labels along lines are a rendering problem worth doing
  properly rather than approximately.
- **No feature (spring, camp) markers.** `features` is empty in the graph.
- **The map does not re-fit when a leg is added.** It fits on load and when a shared
  route opens. Re-fitting on every click would fight the user's own panning.
