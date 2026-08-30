# Example instance — illustrative only

**Every value in this directory is invented.** Coordinates, distances, elevation figures,
Forest Service numbers and junction names are placeholders chosen to exercise the schema,
not surveyed data and not trail information. Nothing here has been walked, measured, or
verified, and none of it should ever be published or copied into a real artifact.

Real data arrives from the curation pass
([#15](https://github.com/jacobemerick/mazatzalhiking/issues/15)) and will live elsewhere.

The route modelled is Jacob's own western approach to Club Cabin, used because it
exercises the parts of the schema that are easy to get wrong:

- **a road leg** — FR 479 from the dam to the Davenport trailhead, because road walking
  has to be clickable like anything else
- **a chain of legs** through named junctions, which is what the builder assembles
- **a feature partway along a leg** — Club Cabin at `at: 0.62` on segment `4H`, the case
  that a later split-here action resolves against
- **concurrent trails** — segment `5A` carrying both the Mazatzal Divide Trail and the
  Arizona Trail
- **a tombstone** — a retired id with `superseded_by`, so a stale shared URL is repairable

Validate with:

```
./tools/validate_graph.py schema/example/graph.json
```
