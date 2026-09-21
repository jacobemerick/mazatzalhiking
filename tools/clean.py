#!/usr/bin/env python3
"""Track cleaning: outlier rejection, consensus and jitter removal (#11, #13).

Four operations, in this order:

1. **Spike rejection.** Drop any point more than `spike_perp_m` off the chord between
   its neighbours. 200 points corpus-wide.
2. **Dead-end trimming.** Where a leg ends at a node nothing else joins -- a spring, a
   summit, a trailhead -- the recorded track keeps going after arriving: it mills
   about at the water, loops the summit, walks back to the car. Cut the leg at the
   first point within `arrive_m` of the track's closest approach to the node and end
   it on the node itself.
3. **Consensus.** Where other recorded passes run within `consensus_far_m` of the leg,
   move each point to the weighted mean of every pass's position beside it. One GPS
   track is one sample of where the trail is; N passes averaged are a better one.
4. **Simplification.** Douglas-Peucker at `simplify_m`, set to the horizontal accuracy
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
    spike_perp_m=25.0,       # drop a point this far off the chord between its neighbours
    arrive_m=10.0,           # a dead-end leg has arrived this close to its closest approach
    consensus_near_m=5.0,    # another pass this close gets a full vote...
    consensus_far_m=10.0,    # ...tapering to none here; beyond it is a different line
    consensus_step_m=5.0,    # densify the leg to this spacing before voting
    simplify_m=3.3,          # Douglas-Peucker tolerance ~ device horizontal accuracy
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


def _xy(p, mlat, mlon, o):
    return ((p[1] - o[1]) * mlon, (p[0] - o[0]) * mlat)


def trim_dead_end(pts, node, arrive_m):
    """Cut the tail of a leg that ends at a node nothing else joins.

    `pts` runs toward the dead end; `node` is its (lat, lon). The leg is cut at the
    first point within `arrive_m` of the track's closest approach to the node, and
    the node itself becomes the last point. "Closest approach plus a margin" rather
    than a plain radius, because the node is authored and the track need not reach
    it: at Club Spring and Horse Camp Seep every recorded pass stops ~18 m short of
    the water and mills about there, and a plain radius would keep the whole tangle.

    Returns (points, index_of_last_recorded_point_kept).
    """
    if len(pts) < 2:
        return list(pts), len(pts) - 1
    mlat, mlon = _m_per_deg(node[0])
    d = [math.hypot(*_xy(p, mlat, mlon, node)) for p in pts]
    tol = min(d) + arrive_m
    i = max(1, next(i for i in range(len(pts)) if d[i] <= tol))
    ele = pts[i][2] if len(pts[i]) > 2 else None
    end = (node[0], node[1], ele) if ele is not None else (node[0], node[1])
    return list(pts[:i + 1]) + [end], i


class PassIndex:
    """Grid index over every recorded track, for finding the passes beside a point.

    Built once per rebuild over the despiked corpus. `beside()` returns, for one query
    point, the nearest point on each *pass* within `far_m`: a track that runs through
    the same place twice (an out-and-back, a loop) is two passes, told apart by a gap
    in point index.
    """
    CELL = 20.0
    PASS_GAP = 25       # points; index gap that separates two passes of one track

    def __init__(self, tracks, far_m):
        self.tracks = {t['key']: t['pts'] for t in tracks}
        first = next(iter(self.tracks.values()))[0]
        self.o = (first[0], first[1])          # flat-frame origin; the range is small
        self.mlat, self.mlon = _m_per_deg(first[0])
        self.far = far_m
        self.reach = int(math.ceil(far_m / self.CELL))
        self.xy = {k: [_xy(p, self.mlat, self.mlon, self.o) for p in pts]
                   for k, pts in self.tracks.items()}
        self.grid = {}
        for k, ps in self.xy.items():
            for i, (x, y) in enumerate(ps):
                self.grid.setdefault((int(x // self.CELL), int(y // self.CELL)), []).append((k, i))

    def to_xy(self, p):
        return _xy(p, self.mlat, self.mlon, self.o)

    def to_ll(self, x, y):
        return (y / self.mlat + self.o[0], x / self.mlon + self.o[1])

    @staticmethod
    def _proj(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        if L2 == 0:
            return math.hypot(px - ax, py - ay), ax, ay
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
        qx, qy = ax + t * dx, ay + t * dy
        return math.hypot(px - qx, py - qy), qx, qy

    def beside(self, x, y, exclude=None):
        """Nearest point on each pass within far_m of (x, y).

        `exclude` is (track_key, i0, i1): the leg's own arc, which must not vote for
        itself. Returns a list of (track_key, distance, qx, qy).
        """
        cx, cy = int(x // self.CELL), int(y // self.CELL)
        hits = {}
        for i in range(cx - self.reach, cx + self.reach + 1):
            for j in range(cy - self.reach, cy + self.reach + 1):
                for k, pi in self.grid.get((i, j), ()):
                    if exclude and k == exclude[0] and exclude[1] <= pi <= exclude[2]:
                        continue
                    ps = self.xy[k]
                    for a, b in ((pi - 1, pi), (pi, pi + 1)):
                        if a < 0 or b >= len(ps):
                            continue
                        d, qx, qy = self._proj(x, y, *ps[a], *ps[b])
                        if d <= self.far:
                            hits.setdefault(k, []).append((pi, d, qx, qy))
        out = []
        for k, hs in hits.items():
            hs.sort()
            run = [hs[0]]
            for h in hs[1:]:
                if h[0] - run[-1][0] > self.PASS_GAP:
                    best = min(run, key=lambda h: h[1]); out.append((k, best[1], best[2], best[3]))
                    run = []
                run.append(h)
            best = min(run, key=lambda h: h[1]); out.append((k, best[1], best[2], best[3]))
        return out


def densify(pts, step_m, mlat, mlon):
    """Insert points so no gap exceeds step_m. Every original vertex is kept, which is
    what makes this safe: resampling from scratch clips corners and lost 1-2% of
    length on legs the consensus step never touched."""
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        L = math.hypot((b[1] - a[1]) * mlon, (b[0] - a[0]) * mlat)
        n = max(1, int(math.ceil(L / step_m)))
        for k in range(1, n + 1):
            f = k / n
            out.append(tuple(a[j] + f * (b[j] - a[j]) for j in range(len(a))))
    return out


def consensus(pts, index, exclude, near_m, far_m, step_m, pin=(0, -1)):
    """Move each point of a leg to the weighted mean position across every pass.

    The leg itself votes with weight 1. Each other pass within `far_m` votes with
    weight 1 up to `near_m`, tapering linearly to 0 at `far_m` -- the taper is what
    stops the line kinking where a pass enters or leaves the band, and the cut-off is
    what makes a genuine detour (a side trip to a seep) exclude itself rather than
    drag the tread toward it. Movement is along the local normal only, so the leg
    cannot slide along itself. Points in `pin` (default: both ends) never move; ends
    are node positions, which are authored.

    Returns (points, stats) where stats has the passes that voted and how much the
    line moved.
    """
    mlat, mlon = index.mlat, index.mlon
    pts = densify(pts, step_m, mlat, mlon)
    n = len(pts)
    xy = [index.to_xy(p) for p in pts]
    pinned = {i % n for i in pin}
    out = list(pts)
    voters, shifts, voted = set(), [], 0
    for k in range(n):
        if k in pinned or k == 0 or k == n - 1:
            continue
        (ax, ay), (x, y), (bx, by) = xy[k - 1], xy[k], xy[k + 1]
        tx, ty = bx - ax, by - ay
        L = math.hypot(tx, ty)
        if L == 0:
            continue
        nx, ny = -ty / L, tx / L
        W, S = 1.0, 0.0
        for key, d, qx, qy in index.beside(x, y, exclude):
            w = 1.0 if d <= near_m else (far_m - d) / (far_m - near_m)
            W += w
            S += w * ((qx - x) * nx + (qy - y) * ny)
            voters.add(key)
        if W > 1.0:
            voted += 1
        sh = S / W
        shifts.append(abs(sh))
        la, lo = index.to_ll(x + sh * nx, y + sh * ny)
        out[k] = (la, lo) + tuple(pts[k][2:])
    stats = dict(passes=sorted(voters),
                 voted_fraction=round(voted / max(1, n - 2), 3),
                 mean_shift_m=round(sum(shifts) / max(1, len(shifts)), 2),
                 max_shift_m=round(max(shifts), 2) if shifts else 0.0)
    return out, stats


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
