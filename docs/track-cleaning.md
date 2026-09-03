# Track cleaning

Decision record for [#11](https://github.com/jacobemerick/mazatzalhiking/issues/11).
Implementation in [`tools/clean.py`](../tools/clean.py).

**Decision: reject spikes geometrically, then simplify at 3.3 m. No moving average.**

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

**Still outstanding:** the ticket also asks that the result be spot-checked by eye on a
map before the settings are locked in. That has not been done — the numbers above are the
statistical half of the verification only.
