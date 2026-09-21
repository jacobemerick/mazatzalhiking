# Track cleaning

Decision record for [#11](https://github.com/jacobemerick/mazatzalhiking/issues/11).
Implementation in [`tools/clean.py`](../tools/clean.py).

**Decision: reject spikes geometrically, trim dead ends, average across every recorded
pass within 10 m, then simplify at 3.3 m. No moving average.**

The consensus step was added 2026-09-21, after the graph was curated; it is the surviving
half of [#13](https://github.com/jacobemerick/mazatzalhiking/issues/13).

## What the corpus actually contains

The ticket anticipates four problems. Measured over all 54,962 recorded points, two of
them do not exist here:

| | |
|---|---|
| exact-duplicate positions | **0** |
| steps under 1 m | 93 (0.2%) |
| largest single step | 327 m |
| median step | 12.8 m |
| points sitting off the line between their neighbours | 32 |

There are **no stationary clusters** — both recorders were already distance-filtered — and
**no teleports**; the step distribution is smooth, with no separate population of
impossible jumps. So cleaning here is two narrow operations rather than a pipeline.

## Timestamps cannot be used

The ticket asks to drop "points implying impossible speed". Nine trips have no time
source at all, and eleven more only have times recoverable from the bulk export
([#10](https://github.com/jacobemerick/mazatzalhiking/issues/10)), so speed is not
computable for most of the corpus. A rule covering a fifth of the data is worse than a
geometric rule covering all of it. Outlier rejection here is purely geometric: a point
more than 25 m off the chord between its neighbours is dropped. That removes 200 points.

Two details that matter more than they look:

- **Judge every point against its original neighbours, in one pass.** Judging against the
  last *surviving* neighbour seems more thorough and is much worse: one drop widens the
  chord the next point is measured against, making that one likelier to drop too. The
  cascade ate 252 points, 85 from a single track, and dragged leg ends up to 300 m from
  their junctions.
- **Pin the points the graph depends on.** Node positions are authored truth and a derived
  step may not move them, so the points a junction was snapped to — and the endpoints of
  every traced arc — are never dropped. Without that pin an erratic stretch takes its
  neighbours with it and the nearest survivor is an unacceptable distance away.

## Simplification, not a moving average

The obvious smoother — a 3-point weighted average, capped so no point moves far from
where it was recorded — was built first and rejected on measurement. The cap was meant
to protect switchbacks: jitter is small and gets pulled in; a real corner is a large
excursion, so the cap binds and the corner survives. **It does not work that way.** At a
1 m cap, 89% of points sat pinned at the cap, so it was not discriminating corners from
noise at all — it was a uniform shrink dial.

Measured over the same corpus, against Douglas-Peucker:

| method | length lost | curvature removed |
|---|---:|---:|
| 3-point average, 1 pass, 1 m cap | 2.90% | 26.1% |
| 3-point average, 2 passes, 4 m cap | 6.22% | 56.9% |
| **Douglas-Peucker, 3.3 m** | **1.92%** | **36.5%** |

Simplification removes substantially more noise per unit of real distance surrendered,
because it discriminates by *scale* rather than by displacement. That is exactly the
switchback guarantee the ticket asks for: no original point ends up further than the
tolerance from the retained line, so a switchback whose amplitude exceeds 3.3 m cannot be
cut, while jitter below it disappears. Verified against the corpus — worst actual
deviation 3.30 m.

**The tolerance is an accuracy decision, not a storage decision.** 3.3 m is the horizontal
accuracy of the recording devices, which is what makes the retained line the honest one.
It also shrinks the files; that is a side effect and must not become the reason, or
published mileage turns into a function of a storage tuning knob.

## Verification

The ticket asks for cleaned mileage compared against raw, and it moved:

| | before | after |
|---|---:|---:|
| network distance | 317.9 mi | **311.7 mi** (−1.95%) |
| network gain | 90,513 ft | **85,420 ft** (−5.6%) |
| points stored | 16,189 | 15,035 |

Two separate causes, worth keeping apart. The distance change is cleaning: jitter makes a
recorded track a random walk around the true line, and a random walk is always longer.
The gain change is mostly *not* cleaning — it is the switch to DEM elevation
([#12](https://github.com/jacobemerick/mazatzalhiking/issues/12)).

## Consensus across passes

A single GPS track is one noisy sample of where the trail is. Where the same ground was
walked more than once, the passes are independent samples and their mean is a better
line than any one of them — error falls with the square root of the count. The corpus
inventory found 27% of the ground walked twice; measured against the curated legs, **32%
of the network has another recorded pass within 10 m** (25% within 5 m), so a third of
the network can be improved this way and two-thirds cannot.

The rule, per leg: densify the traced line to 5 m spacing, and at every point find the
nearest point on each other pass within 10 m. The leg votes with weight 1; each other
pass votes with weight 1 out to 5 m, tapering to 0 at 10 m. The point moves along its
local normal to the weighted mean. A track's return leg on an out-and-back counts as a
separate pass; the leg's own arc is excluded so it cannot vote for itself. Both ends are
pinned, because they are node positions and nodes are authored.

Three details that matter:

- **Densify, never resample.** The first cut replaced the vertices with a fresh 5 m
  resample and clipped every corner: legs the consensus never touched lost 1–2% of their
  length. Keeping every original vertex and inserting between them costs nothing on
  untouched legs (worst case −0.5%, most under 0.1%).
- **The taper is what keeps the line smooth.** With a hard 10 m gate, a pass entering the
  band moves the mean by up to 5 m in one step. Tapering the weight to zero at the edge
  makes the entry continuous.
- **The cut-off is what keeps detours out.** A side trip to a seep leaves the band and
  stops voting; it cannot drag the tread toward it. This is the same finding as before —
  smoothing cannot remove excursions, and does not try to — expressed as a limit on what
  may vote rather than as a window size.

Measured: 63 legs have votes on more than 5% of their points, the mean shift on a voted
leg is 1–2 m, the largest single shift anywhere is 4.7 m, and network distance falls a
further 0.30% (311.7 → 310.8 mi) — jitter that survived simplification because it was
consistent along one track but not between tracks. Checked by eye over aerial imagery
on the upper Barnhardt Trail (8 passes), Deer Creek, Rock Creek, and the spurs below:
the consensus line sits inside the bundle of passes and on the visible tread.

## Dead ends

A leg that ends where nothing else joins — a spring, a summit, a trailhead — is traced
from a track that did not stop on arrival. It milled about at the water, looped the
summit, walked back to the car. The Club Ranch Spur ended in six points zigzagging in a
15 m box at Club Spring; the Mount Peeley Spur carried 100 m of summit wandering.

The rule: walking toward the dead end, cut at the first point within 10 m of the
track's *closest approach* to the node, and end the leg on the node itself. Closest
approach plus a margin rather than a plain radius, because the node is authored and the
track need not reach it — at Club Spring and Horse Camp Seep every recorded pass stops
~18 m short of the water, and a plain 10 m radius would keep the whole tangle. Sixteen
legs are trimmed, most by 0–2 points; the dead-end legs now all end exactly on their node.

This is applied only at degree-1 nodes. At a through junction the arc endpoint is the
snapped point, and wandering there would show in both adjoining legs; none has been seen.

## Spot check

The ticket asks that the result be checked by eye on a map before the settings are
locked in. Done 2026-09-21 for the consensus and dead-end steps, over aerial imagery,
on the legs named above. The spike and simplification settings have still only been
verified statistically.
