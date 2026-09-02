# Junction curation tool

[#14](https://github.com/jacobemerick/mazatzalhiking/issues/14). Local authoring only —
this does not ship with the site and has no bearing on the deployed Worker, which still
serves nothing but `public/`.

```
./tools/curate/server.py      # then open http://localhost:8723
```

Python stdlib plus Leaflet from a CDN. No install step, no build.

## Why this runs before the pipeline is finished

#14 asks for "cleaned canonical lines," which #10, #11 and #13 have not produced yet. It
does not have to wait, because of how the schema splits authored truth from derived data:
**node coordinates are authored, segment geometry is derived.** A junction placed against a
raw recorded track stays in exactly the right place when cleaning and traversal-merging
later change the lines underneath — only the derived geometry is recomputed.

So the durable output of curation is node positions, which nodes connect to which, and
what the legs are called. None of that is invalidated by the pipeline landing afterwards.
The distances and elevation figures written today *are* provisional, and will be recomputed
from the canonical lines once #13 exists.

## Using it

| | |
|---|---|
| <kbd>N</kbd> | place a junction — click near a track |
| <kbd>S</kbd> | make a segment — click one junction, then another |
| <kbd>Esc</kbd> | back to panning, or dismiss the form |
| <kbd>⌘Z</kbd> | undo |

**Clicks snap to the recorded tread.** A click within 60 m moves onto the nearest recorded
point; further out it is refused rather than inventing a junction in open country. The form
then shows every pass through the point and on what dates, which is usually how you recognise
what junction you are looking at. A trip listed twice doubled back through here — worth
noticing, for the reason below.

**Segments trace along a real recorded track.** Picking two junctions finds the tracks that
pass through both and follows one between them, so a leg's geometry is ground you actually
walked rather than a straight line. The chosen track is recorded in the segment's `sources`.

**A track can run between two junctions more than one way**, and this is the tool's sharpest
edge. On a loop or an out-and-back a trip comes through the same junction twice, so the two
endpoints can land on different visits and the sub-path between them runs most of the way
round the loop — a two-tenths-of-a-mile hop recorded as thirty miles. So the form enumerates
every arc, labels each with its length, and defaults to the shortest, which is the leg where
the alternative is the rest of the loop. Among arcs that are effectively the same leg
recorded on different trips, the tightest snap wins instead.

**The candidate leg is drawn on the map in orange before you save it**, and pulled into view
if it does not already fit. A wrong way round is obvious as a line and invisible as a number,
so look at the line.

Distance and elevation come from the traced points. Gain uses the direction-symmetric
algorithm the schema prescribes — simplify the profile, then sum — so reversing a segment
swaps gain and loss exactly.

Everything saves after every change, so a sitting can be abandoned and resumed. Writes are
atomic: an interrupted save cannot truncate the work.

## Output

```
curation/
  graph.json          nodes, segments, trails — schema-valid, no point data
  geometry/<id>.json  one file per segment
```

`curation/` is committed as of the first full pass over the range. The real judgment lives
there rather than in this tool — what counts as a junction worth modelling. A wash crossing
is not one; a trail you could actually turn onto is. Equally, not every stretch of recorded
track becomes a segment: off-trail wanders and roads best left off the map are walked ground
that is deliberately absent.

Check the output at any point with:

```
./tools/validate_graph.py curation/graph.json
```

## Known limits

- **A segment needs one recorded track running through both its junctions.** Where no single
  trip covers the stretch, the tool says so and asks for an intermediate junction. Stitching
  a leg across two trips is not supported yet; whether that is worth building depends on how
  often it comes up in practice.
- **Features (springs, cabins, camps) cannot be placed yet.** The schema supports them and
  the builder will show them, but the UI covers junctions and segments first, since those are
  what the network is made of.
- **No editing or deletion.** Undo covers mistakes made in a sitting; correcting an earlier
  sitting means editing `curation/graph.json` by hand for now. Worth adding if it becomes
  annoying — and note the schema's rule that re-splitting a leg retires its id rather than
  reusing it.
