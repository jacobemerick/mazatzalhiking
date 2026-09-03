#!/usr/bin/env python3
"""Track cleaning: outlier rejection and jitter removal (#11).

Two operations, in this order:

1. **Spike rejection.** Drop any point more than `spike_perp_m` off the chord between
   its neighbours. 200 points corpus-wide.
2. **Simplification.** Douglas-Peucker at `simplify_m`, set to the horizontal accuracy
   of the recording devices. This is the jitter filter, and it guarantees no original
   point ends up further than the tolerance from the retained line -- which is what
   keeps switchbacks intact.

There is deliberately no moving average, no stationary-cluster handling and no
speed-based outlier test; the corpus has no stationary clusters, the smoother was
measured and rejected, and most trips carry no timestamps to compute speed from.

Rationale, measurements and the alternatives that were tried and dropped:
docs/track-cleaning.md
"""
import math

# Recorded into every geometry file this produces, so any output can be traced
# back to the settings that made it.
DEFAULTS = dict(
    spike_perp_m=25.0,   # drop a point this far off the chord between its neighbours
    simplify_m=3.3,      # Douglas-Peucker tolerance ~ device horizontal accuracy
)


def _m_per_deg(lat):
    """Local metres-per-degree, so the work can be done in a flat local frame."""
    return (111132.92 - 559.82 * math.cos(2 * math.radians(lat))
            + 1.175 * math.cos(4 * math.radians(lat)),
            111412.84 * math.cos(math.radians(lat))
            - 93.5 * math.cos(3 * math.radians(lat)))


def _perp(p, a, b, mlat, mlon):
    """Perpendicular distance in metres from p to the segment a-b."""
    ax, ay = (a[1] - p[1]) * mlon, (a[0] - p[0]) * mlat
    bx, by = (b[1] - p[1]) * mlon, (b[0] - p[0]) * mlat
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(ax, ay)
    t = max(0.0, min(1.0, -(ax * dx + ay * dy) / L2))
    return math.hypot(ax + t * dx, ay + t * dy)


def drop_spikes(pts, perp_m, protect=()):
    """Remove points sitting off the line between their neighbours.

    Every point is judged against its *original* neighbours and the drops are applied
    in one pass. Judging against the last surviving neighbour instead looks more
    thorough and is much worse: one drop widens the chord the next point is measured
    against, which makes that one likelier to drop too, and the cascade eats whole
    runs of good track. Measured on this corpus, chaining removed 252 points -- 85 of
    them from a single track -- and dragged segment endpoints up to 300 m off their
    junctions.

    Endpoints are never dropped: a track's first and last point are where the walk
    started and stopped. Neither are indices in `protect`, which the caller uses to
    pin the points its junctions were snapped to -- node coordinates are authored
    truth, and a derived step is not allowed to move them. Without that pin, an
    erratic stretch can take a run of neighbouring points with it and leave the
    nearest survivor an unacceptable distance from the junction.

    Returns (kept_points, kept_original_indices).
    """
    if len(pts) < 3:
        return list(pts), list(range(len(pts)))
    mlat, mlon = _m_per_deg(pts[len(pts) // 2][0])
    pin = set(protect)
    idx = [0] + [i for i in range(1, len(pts) - 1)
                 if i in pin
                 or _perp(pts[i], pts[i - 1], pts[i + 1], mlat, mlon) <= perp_m] + [len(pts) - 1]
    return [pts[i] for i in idx], idx


def simplify(pts, tol_m, _idx=None):
    """Douglas-Peucker in metres, iterative so a long track cannot blow the stack.

    Returns (kept_points, kept_indices_into_pts).
    """
    n = len(pts)
    if n < 3:
        return list(pts), list(range(n))
    mlat, mlon = _m_per_deg(pts[n // 2][0])
    keep = [False] * n
    keep[0] = keep[n - 1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        worst, wi = -1.0, -1
        for i in range(a + 1, b):
            d = _perp(pts[i], pts[a], pts[b], mlat, mlon)
            if d > worst:
                worst, wi = d, i
        if worst > tol_m:
            keep[wi] = True
            stack.append((a, wi)); stack.append((wi, b))
    idx = [i for i in range(n) if keep[i]]
    return [pts[i] for i in idx], idx


def clean(pts, **cfg):
    """Full pass. Returns (cleaned_points, kept_original_indices)."""
    c = config(**cfg)
    kept, i1 = drop_spikes(pts, c['spike_perp_m'])
    out, i2 = simplify(kept, c['simplify_m'])
    return out, [i1[i] for i in i2]


def config(**cfg):
    c = dict(DEFAULTS); c.update(cfg); return c
