# Elevation

Decision record for [#12](https://github.com/jacobemerick/mazatzalhiking/issues/12).
Implementation in [`tools/elevation.py`](../tools/elevation.py); applied by
[`tools/build_geometry.py`](../tools/build_geometry.py).

**Decision: gain and loss are derived from USGS 3DEP resampled along the cleaned
geometry, with a 3 m threshold. Recorded device elevation stays in the archive and is
not what the site publishes.**

## The measurement

Recorded elevation was compared against 3DEP at all 16,189 points of the committed
network, on identical geometry, so the only variable is the elevation source.

| | |
|---|---|
| 3DEP coverage of the network | 16,189 / 16,189 points, **every one at 1 m lidar** |
| recorded minus DEM, median | −0.2 m |
| recorded minus DEM, mean | −0.5 m |
| recorded minus DEM, stdev | 4.2 m |
| within 5 m / 10 m / 25 m | 79.6% / 96.8% / 100% |
| worst single point | 34.6 m |

## Why the DEM wins

**The device is not biased — it is noisy, and noise only ever inflates gain.** A median
disagreement of −0.2 m over 16,189 points says the recorded elevations are centred on
the truth, so the argument for the DEM is not that the altimeter was wrong on average.
It is that gain is a *rectified* sum: every wobble contributes its rise and its fall is
discarded. Noise therefore adds to the total and can never subtract from it. Measured
over the same points:

| threshold | recorded | DEM | difference |
|---|---:|---:|---:|
| naive | 97,067 ft | 90,910 ft | −6.3% |
| **3 m** | 92,356 ft | **86,059 ft** | −6.8% |
| 5 m | 88,596 ft | 83,601 ft | −5.6% |
| 10 m | 82,487 ft | 79,289 ft | −3.9% |

The DEM is lower at every threshold, and none of that excess was climbing anyone did.

**Every recorded elevation in the corpus is a whole number of metres.** All 25 files,
both exporters, 54,962 points, zero exceptions. Sub-metre precision was already gone
before the data reached this repo, so nothing is being given up by not using it. A 1 m
lidar surface has a vertical RMSE around a tenth of a metre; the recorded channel cannot
resolve better than one.

**The corpus spans two devices and ten years.** Barometric drift differs per device, per
day and per weather, so recorded gain is not comparable between trips. Every segment
measured against one common surface is. That matters here specifically, because a route's
gain is the sum over its legs and those legs come from different trips — a figure summed
from mismatched sources is wrong in a way no single number reveals.

## Why 3 m

The threshold's original job was suppressing recorded-elevation noise. On a 1 m lidar
surface that noise is gone, so the threshold reverts to its real purpose: discarding
micro-relief a hiker would not call climbing. That justifies sitting lower than the 5 m
the curation tool used provisionally, and 3 m is the conventional figure for hiking gain.

## The algorithm is unchanged

Schema decision 3 still holds and now applies to the DEM profile: **simplify the
elevation profile first, then sum.** Collapse any monotone run smaller than the
threshold, then sum the rises for gain and the falls for loss. Profile simplification is
order-independent, so the simplified profile read backwards is the forward one reversed —
gain forward is exactly loss backward, and two stored numbers per segment cover both
directions.

## What this costs

Regenerating needs the network, because the DEM is sampled from the USGS 3DEP
ImageServer rather than a local raster. Acceptable on two counts: it is authoring-time
only — the deployed Worker still serves nothing but `public/` — and every sampled value
is committed to [`archive/dem-3dep.json`](../archive/dem-3dep.json), so rebuilding the
committed tree needs no network at all. Only genuinely new coordinates cost a request.

## Known limitation

The DEM is sampled at the recorded horizontal positions, so it inherits their horizontal
error. On a steep sideslope a few metres of horizontal error is several metres of
elevation error, and unlike the recorded channel that error is *correlated* with terrain
rather than random. This is the main reason cleaning
([#11](https://github.com/jacobemerick/mazatzalhiking/issues/11), see
[`track-cleaning.md`](track-cleaning.md)) runs first and why its tolerance is tied to
device accuracy rather than to file size. It is not eliminated, and it is the thing to
revisit if a gain figure ever looks wrong on the ground.
