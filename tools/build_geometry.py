#!/usr/bin/env python3
"""Rebuild segment geometry and statistics from the archive (#11, #12).

    ./tools/build_geometry.py           # rebuild in place
    ./tools/build_geometry.py --dry-run # report what would change, write nothing

Authoring-time only. Reads `archive/` and the authored parts of `curation/graph.json`
and rewrites the derived parts: every `curation/geometry/<id>.json`, plus each
segment's `miles`, `gain_ft` and `loss_ft`.

## What is authored and what is derived

`graph.json` holds the judgments a person made -- where the junctions are, which of
them connect, what the legs are called, which recorded trip a leg was traced from.
None of that is touched here. Geometry, distance and elevation are derived, and are
regenerated wholesale on every run.

## Which recorded arc a segment came from

A leg is a sub-path of one recorded track, and a track can run between the same two
junctions more than one way -- on a loop or an out-and-back the endpoints can land on
different visits, so the "wrong" arc is most of the way round the loop rather than the
two-tenths of a mile intended. Picking that arc was a human decision made in the
curation tool, and it must not be re-guessed here.

So the arc is **recorded into the geometry file** as track key and endpoint indices
into the immutable archive, and read straight back on later runs. The first run, over
geometry written before this tool existed, recovers it instead by replaying the old
simplification against every candidate arc and keeping the one that reproduces the
committed line exactly. That recovery is verified: all 104 segments matched.

## Why the numbers change

Before this tool, `miles` and `gain_ft` were computed from the full recorded point
list while `coordinates` stored a simplified line, so **a segment's stored figures
could not be reproduced from its own geometry** -- the committed lines were 1.1%
shorter than the mileage they claimed. Everything here is computed from the line that
actually gets written, so the artifact is self-consistent and #16 can check it.
"""
import json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'curate'))

from inventory import load, hav, M2MI, M2FT
import clean as C
import elevation as E
import server as CURATE          # for rdp(), to replay pre-existing geometry

GPX = os.path.join(ROOT, 'archive', 'gpx')
GRAPH = os.path.join(ROOT, 'curation', 'graph.json')
GEOM = os.path.join(ROOT, 'curation', 'geometry')

DRY = '--dry-run' in sys.argv


def corpus():
    """Raw tracks, straight from the archive."""
    tracks = []
    trips, _ = load(GPX)
    for t in trips:
        for si, seg in enumerate(t['segs']):
            tracks.append(dict(key=f"{t['file']}#{si}", file=t['file'], date=t['date'],
                               pts=[(p[0], p[1], p[2]) for p in seg]))
    return tracks


def recover_arc(seg, coords, tracks):
    """Find the (track, i0, i1) whose old simplification is exactly this line."""
    fmt = lambda ps: [[round(p[1], 6), round(p[0], 6)] for p in CURATE.rdp(ps, 0.00003)]
    f = seg['sources'][0]['file']
    occ = {}
    for t in tracks:
        if t['file'] != f:
            continue
        for i, (la, lo, _) in enumerate(t['pts']):
            occ.setdefault((round(lo, 6), round(la, 6)), []).append((t, i))
    heads = occ.get(tuple(coords[0]), [])
    tails = occ.get(tuple(coords[-1]), [])
    for th, i in heads:
        for tt, j in tails:
            if th is not tt or abs(i - j) < 1:
                continue
            a, b = sorted((i, j))
            sl = th['pts'][a:b + 1]
            if fmt(sl) == coords or fmt(sl[::-1]) == coords:
                return dict(track=th['key'], **{'from': a, 'to': b}, reversed=i > j)
    return None


def main():
    tracks = corpus()
    by_key = {t['key']: t for t in tracks}
    cfg = C.config()

    graph = json.load(open(GRAPH))
    nodes = {n['id']: n for n in graph['nodes']}
    cache = E.load_cache()
    before = dict(miles=sum(s['miles'] for s in graph['segments']),
                  gain=sum(s['gain_ft'] for s in graph['segments']))
    recovered = reused = 0
    drift = []
    lines = {}

    # Arcs are resolved against the raw archive first, because their endpoints have
    # to be pinned through spike rejection along with the node positions. A junction
    # is snapped to a point on one track, but a leg may be traced from a different
    # trip, so the arc's endpoint on *that* track is a distinct point that the node
    # coordinate alone does not protect. Dropping it moves the end of the drawn leg
    # away from the junction it is supposed to meet.
    arcs = {}
    for seg in graph['segments']:
        old = json.load(open(os.path.join(ROOT, 'curation', seg['geometry'])))
        arc = (old.get('derived') or {}).get('arc')
        if arc:
            reused += 1
        else:
            arc = recover_arc(seg, [c[:2] for c in old['coordinates']], tracks)
            if arc is not None:
                recovered += 1
        if arc is None:
            print(f"  !! {seg['id']}: cannot recover which arc produced this line")
            continue
        arcs[seg['id']] = arc

    pinned = {(round(n['lon'], 6), round(n['lat'], 6)) for n in graph['nodes']}
    ends = {}
    for arc in arcs.values():
        ends.setdefault(arc['track'], set()).update((arc['from'], arc['to']))

    # Spike rejection is a property of the track, so it happens once per track and
    # the arc indices are remapped onto what survives.
    despiked, remap = {}, {}
    for t in tracks:
        protect = set(ends.get(t['key'], ()))
        protect.update(i for i, (la, lo, _) in enumerate(t['pts'])
                       if (round(lo, 6), round(la, 6)) in pinned)
        kept, idx = C.drop_spikes(t['pts'], cfg['spike_perp_m'], protect)
        despiked[t['key']] = kept
        remap[t['key']] = ({old: new for new, old in enumerate(idx)}, idx)

    for seg in graph['segments']:
        arc = arcs.get(seg['id'])
        if arc is None:
            continue

        t = by_key[arc['track']]
        m, idx = remap[arc['track']]
        near = lambda i: m.get(i) if i in m else min(range(len(idx)), key=lambda k: abs(idx[k] - i))
        a, b = sorted((near(arc['from']), near(arc['to'])))
        pts = despiked[arc['track']][a:b + 1]
        if arc['reversed']:
            pts = pts[::-1]
        pts, _ = C.simplify(pts, cfg['simplify_m'])     # endpoints always retained
        lines[seg['id']] = (seg, arc, pts)

    # One batched pass over the DEM for every point in the rebuild.
    allpts = [(round(p[1], 6), round(p[0], 6)) for _, _, pts in lines.values() for p in pts]
    need = len({E.key(x, y) for x, y in allpts} - set(cache))
    if need:
        print(f'sampling {need:,} new points from 3DEP...')
    _, cache = E.sample(allpts, cache,
                        progress=lambda d, n: print(f'  {d:,}/{n:,}', flush=True))

    missing = 0
    for sid, (seg, arc, pts) in lines.items():
        # Everything below is derived from the rounded values that actually get
        # written, never from the full-precision ones. Deriving from the latter
        # produces an artifact that cannot reproduce its own numbers -- which is
        # the exact defect this rebuild exists to fix. The gain threshold makes
        # this matter more than the rounding suggests: collapsing a run is a
        # decision at a boundary, so a centimetre can flip it and move the total
        # by several feet.
        coords = []
        for p in pts:
            lon, lat = round(p[1], 6), round(p[0], 6)
            e = cache.get(E.key(lon, lat))
            if e is None:
                missing += 1
            coords.append([lon, lat, round(e, 1) if e is not None else None])
        cum = [0.0]
        for i in range(1, len(coords)):
            cum.append(cum[-1] + hav((coords[i-1][1], coords[i-1][0]),
                                     (coords[i][1], coords[i][0])))
        cum = [round(c, 1) for c in cum]
        gain, loss = E.profile_gain_loss([c[2] for c in coords])
        for nid, end in ((seg['from'], pts[0]), (seg['to'], pts[-1])):
            n = nodes.get(nid)
            if n:
                d = hav((n['lat'], n['lon']), (end[0], end[1]))
                if d > 1.0:
                    drift.append((sid, nid, d))
        seg['miles'] = round(cum[-1] * M2MI, 2)
        seg['gain_ft'] = round(gain * M2FT)
        seg['loss_ft'] = round(loss * M2FT)
        out = {
            'type': 'LineString',
            'coordinates': coords,
            'cum_m': cum,
            'derived': {
                'arc': arc,
                'source': seg['sources'][0],
                'elevation': 'USGS 3DEP, bilinear (see tools/elevation.py)',
                'gain_threshold_m': E.THRESHOLD_M,
                'cleaning': cfg,
            },
        }
        if not DRY:
            tmp = os.path.join(GEOM, f'.{sid}.tmp')
            with open(tmp, 'w') as f:
                json.dump(out, f, separators=(',', ':'))
            os.replace(tmp, os.path.join(GEOM, f'{sid}.json'))

    after = dict(miles=sum(s['miles'] for s in graph['segments']),
                 gain=sum(s['gain_ft'] for s in graph['segments']))
    if not DRY:
        tmp = GRAPH + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(graph, f, indent=2)
            f.write('\n')
        os.replace(tmp, GRAPH)

    print(f'\narc provenance: {reused} read from geometry, {recovered} recovered from the old line')
    print(f'points with no DEM value: {missing}')
    print(f"miles   {before['miles']:.1f} -> {after['miles']:.1f} "
          f"({100*(after['miles']-before['miles'])/before['miles']:+.2f}%)")
    print(f"gain_ft {before['gain']:,} -> {after['gain']:,} "
          f"({100*(after['gain']-before['gain'])/before['gain']:+.1f}%)")
    if drift:
        # Pre-existing, not caused by the rebuild: the curation tool snaps a junction
        # to a point on one track but may trace the leg from a different trip, taking
        # the nearest point on *that* track within its 40 m tolerance. The two are
        # different points. Recorded here because it is a real gap between a node and
        # the legs meeting it, and it belongs to #16 rather than to this tool.
        print(f'\nleg ends not coincident with their junction ({len(drift)} of '
              f'{2*len(lines)} endpoints, pre-existing, max 40 m trace tolerance):')
        for sid, nid, d in sorted(drift, key=lambda x: -x[2])[:8]:
            print(f'  segment {sid} node {nid}: {d:.1f} m')
    if DRY:
        print('\n--dry-run: nothing written')


if __name__ == '__main__':
    main()
