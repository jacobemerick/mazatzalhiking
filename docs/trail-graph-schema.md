# Trail graph schema

Closes [#9](https://github.com/jacobemerick/mazatzalhiking/issues/9). Blocks the rest of M2.

- Contract: [`schema/graph.schema.json`](../schema/graph.schema.json)
- Example instance: [`schema/example/`](../schema/example)
- Validator: `./tools/validate_graph.py schema/example/graph.json`

The graph is the single data model the whole project rests on. Everything downstream —
the curation tool, the builder, the exports, any public page — reads this and nothing else.

---

## Shape

Five entity types across two files, and the split between those files matters more than
it looks.

```
graph.json                    observations.json
├── trails      named ways    └── observations   dated condition notes,
├── nodes       junctions,          keyed by the id of a segment,
│               trailheads          node, or feature
├── segments    legs between
│               two nodes
└── features    springs, camps,
                cabins, viewpoints
```

**`graph.json` is generated. `observations.json` is hand-authored and never regenerated.**
Conditions are Jacob's words about real wilderness ([#17](https://github.com/jacobemerick/mazatzalhiking/issues/17),
[#18](https://github.com/jacobemerick/mazatzalhiking/issues/18)); geometry is a pipeline
output that will be recomputed many times as cleaning
([#11](https://github.com/jacobemerick/mazatzalhiking/issues/11)) and merging
([#13](https://github.com/jacobemerick/mazatzalhiking/issues/13)) improve. Keeping them
in separate files means re-running the pipeline can never touch the writing.

That separation is the reason ids have to be stable, and it drives the first decision below.

## Decisions

### 1. Ids are assigned once and recorded, never derived

**Decision: the curation tool mints the next free code from a registry and writes it into
the graph. Ids are never computed from coordinates, ordering, or content.**

The obvious approach — hash the geometry, or number segments in pipeline order — fails
here specifically. Geometry is *expected* to change: #11 will re-tune cleaning parameters,
#13 will re-merge traversals as the approach improves, and elevation may be re-derived
under #12. Any id derived from geometry churns on every one of those runs. Because routes
are shared as URLs made of segment ids
([#22](https://github.com/jacobemerick/mazatzalhiking/issues/22)), churn does not just
cost a rebuild — **it silently breaks links other people are holding.** Numbering by
pipeline order is worse: inserting one junction renumbers everything after it.

So ids are data, not a function of data. The registry lives in `graph.json` itself; the
tool reads the highest allocated code and takes the next.

**Format: base62 (`0-9A-Za-z`), 2 characters minimum — but two ids may never differ only
by case.** Two characters hold 3,844 values on paper. In practice a segment's geometry is
one file per id, and both macOS (APFS) and Windows are case-insensitive by default, so
minting `0a` alongside `0A` makes the two resolve to the same path and the second write
destroys the first silently — the damage itself is undetectable downstream, since
`validate_graph.py` never opens the geometry files. So `mint()` tests uniqueness
case-folded, and the validator rejects a colliding *pair of ids* in any graph it is handed,
whichever filesystem authored it. That leaves
**1,296** usable two-character codes. The corpus suggests somewhere between "many dozens"
and a pessimistic upper bound of ~850 segments, so two characters still cover the network,
though with less margin than the raw base62 count implies; three characters remain
available if that bound is ever approached. A 15-leg shared route costs about 45 characters
of ids. Each entity type has its own id space — a node `4F` and a segment `4F` are
unrelated, and the field name always says which is meant.

The stored format is unchanged and stays case-sensitive: `^[0-9A-Za-z]{2,4}$` still
validates, and ids already allocated in both cases remain legal. Only *allocation* is
constrained.

**Splitting a segment retires its id.** When curation discovers a real junction partway
along an existing leg, that leg does not keep its id for the longer half — that would
silently change what an already-shared URL means. The old id is tombstoned and the halves
get fresh codes:

```json
"retired": [
  { "id": "4H", "superseded_by": ["5C", "5D"], "on": "2026-09-14",
    "reason": "split at Sheep Creek Junction" }
]
```

Retired ids are never reissued. A URL holding `4H` is then repairable rather than broken:
the builder sees the tombstone and can substitute both halves, or say plainly that the
route changed. This costs one line of bookkeeping and is the difference between shared
links aging gracefully and rotting.

### 2. A segment carries a list of parent trails, not one

**Decision: `segments[].trails` is an ordered array of trail ids.**

Confirmed against the ground: named trails here do share tread — the Arizona Trail runs
concurrent with the Mazatzal Divide Trail. A single `trail` field cannot represent that
without either duplicating the segment (which would break connectivity and let a route
traverse the same tread twice) or dropping a name.

**Order is display precedence.** `trails[0]` is the local, specific name — the one a hiker
standing at the junction reads off the sign. Long-distance overlays follow. The builder
labels a leg with `trails[0].name`; the GPX/KML export lists every name, since someone
navigating wants to know the tread they are on is also the AZT.

Roads are trails for this purpose. Jacob's own approach to Club Cabin starts on FR 479, so
the network has to make road walking clickable. `trails[].kind` distinguishes `trail` from
`road` so the UI can style them differently, but they are the same entity and connect
normally.

### 3. Geometry is stored one way, and gain reverses exactly

**Decision: store geometry once, running `from` → `to`, with a single `gain_ft` and
`loss_ft` for that direction. The reverse direction swaps them.**

The ticket asks for gain and loss "in each direction," which sounds like four numbers. It
is two, but only if the gain calculation is direction-symmetric — and the obvious
implementation is not. Threshold algorithms that walk the profile accumulating rises above
a cutoff give different answers forward and backward, because they segment the profile as
they go and that segmentation depends on where they start.

The fix, which #12 should adopt regardless:

> **Simplify the elevation profile first, then sum.** Repeatedly collapse any monotone run
> that rises or falls less than the threshold into its neighbours, until none remain. Then
> sum the rises for gain and the falls for loss.

Profile simplification is order-independent, so the simplified profile read backwards is
identical to the forward one reversed. Gain forward is then *exactly* loss backward, and
two stored numbers are sufficient and consistent. It also removes the noise-accumulation
problem #12 raises, since sub-threshold wiggle is gone before anything is summed.

A route is a sequence of segments, so its total gain is the sum of the per-direction
values, picked by how each leg is traversed. No re-derivation at runtime.

### 4. Conditions attach to any id, in their own file

**Decision: an observation names a `target` — a segment, node, or feature id — plus a
date and Jacob's text.**

Segments carry most of it ("the tread above the saddle is brushy"). But conditions are not
always leg-shaped: a junction can be unsigned and easy to miss, and a spring can be dry.
Those belong on the node or the feature, and forcing them onto a segment loses the
precision that makes the note useful.

Multiple observations per target, newest first, never overwritten — the date is what makes
a note meaningful, so it always travels with the text (#17). The file is authored by hand
and read by the builder popup, the export descriptions, and any future page, so all three
surfaces show the same record and cannot drift.

### 5. A road is a segment only when it was walked

**Decision: a road enters the graph on the same terms as a trail — a recorded track, with
`sources`. A road that merely exists on the map does not, however useful it would be.**

Decision 2 makes roads first-class, and they earn it: FR 201 links three crest trailheads
in 1.47 mi and collapses a 15.7 mi detour, which is the difference between a loop and a
car shuttle. The temptation is then to draw in the road you *know* is there — the graded
roads reaching Fig Trailhead from the Davenport side, say.

Two reasons not to, either sufficient. **Provenance:** every segment carries the file and
date it came from, and an unwalked road has none, so its geometry would have to be
invented — which the curation tool refuses to do by design. **Consequence:** anything in
the graph is clickable, so the builder would hand someone a route down ground nobody has
checked, rendered identically to ground walked twice. "It is on the Forest Service map" is
exactly the secondhand claim this project exists not to make.

The corollary is that the connectors worth adding are *findable*: a walked connector is a
recorded arc between two existing nodes with no third node between them and no segment yet.
That search is exhaustive over the corpus. What it cannot do is judge — the same search
surfaces a road that makes a loop work, a road best left off the map, and a thick bushwhack
down a creek, and nothing in a GPX tells them apart. Generate the candidates mechanically,
decide them by hand.

### 6. An unreachable component is declared, not silenced

**Decision: `islands` records a component deliberately left unconnected, with the reason.
An undeclared split stays an error.**

The connectivity check earns its keep — it has caught a missed 0.08 mi connector between
two trailhead nodes 118 m apart, which nothing else would have. So when a real island turns
up, the fix is not to downgrade the check to a warning.

And real islands exist. Fig Trailhead is reached by kayak across the Verde; the recorded
trip shares no ground with any other, and its far bank is 2.08 mi from the nearest node, so
no walked route reaches it and none ever will without a new trip. That is geography, not a
curation gap.

The crossing itself is **not** a segment. It is not walkable, so it cannot sit in a network
whose legs are summed into a route with no way to say "bring a boat" — and it would not
help anyway, since modelling it only extends the island to the west bank. It belongs in
`observations.json`, attached to the trailhead node: a dated, first-person note about an
entry point, which is what it actually is.

So the island is declared in the graph, listing the component's nodes **exactly**. If it
later grows or shrinks the declaration stops matching and the error returns, which is the
point — the exception is a reviewed act with a date on it, like retiring an id, not a
permanent hole in the check.

## Two constraints the schema has to satisfy

### A route may end partway along its last leg

Jacob's Club Cabin case: the cabin sits partway along the Deadman → Brody leg, and a route
to it should stop there rather than run on to the junction. A later "split here" button
(M5) would let a click drop the remainder.

This is why features are **not** nodes. If every point of interest split its trail, legs
would fragment, every route would take twice the clicks, and the split button would have
nothing to do. Instead a feature records where it is, and that position is precisely what
a split resolves to.

So the schema requires: **a segment must be addressable by fractional position**, and
distance and gain must be computable for a partial leg. Geometry therefore stores
cumulative distance along the line, so a cut at `0.62` is exact and needs no re-measuring.
Nothing in v1 has to *use* this — the builder ships without the button — but the data
model cannot preclude it.

That is now delivered: geometry files carry a `cum_m` array alongside the coordinates.
See [`schema/geometry.schema.json`](../schema/geometry.schema.json) for the contract.

### The client must not download the whole range

[#16](https://github.com/jacobemerick/mazatzalhiking/issues/16) flags this, and it shapes
where geometry lives. Segments hold a *reference* to their geometry, not the points:

| Artifact | Contents | When loaded |
|---|---|---|
| `graph.json` | trails, nodes, segments with stats, features. No point data. | always, once |
| `geometry/display.json` | all segments, simplified for map drawing | on map load |
| `geometry/<id>.json` | one segment, full resolution | only when exporting |

`geometry/display.json` does not exist yet; it belongs to
[#16](https://github.com/jacobemerick/mazatzalhiking/issues/16).

Topology is what the builder actually needs to work — which segments touch which nodes,
how long each is, how much it climbs — and that is small. Full-resolution geometry is
needed only to write a GPX, and only for the dozen or so legs in the route, so it is
fetched per segment at export time. All three are static files, so the deploy stays an
assets-only Worker with no runtime dependency (#8).

## Field reference

See [`schema/graph.schema.json`](../schema/graph.schema.json) for the authoritative
contract. Summary:

**trail** — `id`, `name`, `code` (Forest Service or road number, nullable), `kind`
(`trail` | `road`).

**node** — `id`, `name`, `kind` (`junction` | `trailhead`), `lat`, `lon`, `ele_ft`.
Nodes are the connectivity structure; only nodes split segments.

**segment** — `id`, `name` (human, shown in the builder — "Davenport Trailhead to Sheep
Creek Junction"), `from`, `to` (node ids), `trails` (array, display order), `miles`,
`gain_ft`, `loss_ft` (for `from`→`to`), `geometry` (path), `sources` (the recorded tracks
this leg was derived from, with their dates — the walked-it-myself provenance is the point
of the project and must survive into the graph).

**feature** — `id`, `name`, `kind` (`water` | `camp` | `cabin` | `viewpoint` | `ruin` |
`ford`), `lat`, `lon`, and the derived `on` / `at` placing it along a segment.

**island** — `nodes` (every node id in the isolated component, exactly), `on`, `reason`.
Declares a component no walked route reaches; an undeclared split is an error. See
decision 6.

Coordinates are the authored truth for nodes and features; `on` and `at` are **derived**
at build time by projecting onto the segment. Storing the projection as truth would make
it wrong the moment geometry is refined, whereas "Club Cabin is at this coordinate" stays
true forever.

**observation** (separate file) — `target` (any id), `date`, `text`, `category`
(`brush` | `tread` | `route-finding` | `water` | `access`).

## What this does not decide

- **Segment granularity** — what counts as a junction worth modelling. A wash crossing is
  not a junction; a trail you could actually turn onto is. That judgment is the curation
  pass (#14, #15), and the schema is indifferent to how finely it is drawn.
- **Route URL encoding** — #22. The schema guarantees what encoding needs: short stable
  ids, and fractional addressing for a truncated final leg. A route is a start node plus an
  ordered list of segments; direction falls out of connectivity, since consecutive legs
  share a node.
- **Elevation source** — #12 chooses recorded versus DEM. The schema stores the result
  either way; only the symmetric algorithm above is prescribed.
