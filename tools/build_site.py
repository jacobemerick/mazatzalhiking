#!/usr/bin/env python3
"""Emit the static data artifacts the site serves (#16).

    ./tools/build_site.py           # validate, then write public/data/
    ./tools/build_site.py --check   # validate and compare, write nothing

Reads the authored graph and observations under `curation/` and writes what the
browser fetches under `public/data/`. Nothing is served from `curation/` directly,
and nothing here is authored: every file under `public/data/` is regenerated
wholesale on every run, and the run is idempotent.

## What gets emitted, and why it is split this way

The client must not download the whole range to draw a route, so the artifact is
three tiers (docs/trail-graph-schema.md, "The client must not download the whole
range"):

    public/data/graph.json          topology and stats, no point data   always, once
    public/data/display.json        every segment, simplified for the map   on map load
    public/data/geometry/<id>.json  one segment, full resolution            at export
    public/data/observations.json   the condition records                   always, once

`graph.json` is the curated graph minus nothing: the geometry path and the source
tracks stay, because provenance is the point and the builder shows it. `display.json`
is coordinates only, Douglas-Peucker'd for screen use; the full line is fetched per
leg only when writing a GPX. Geometry files are copied whole, `derived` included.

## What is checked before anything is written

`validate_graph.py` runs first and any error aborts the build, so a broken graph
cannot ship quietly. On top of the topology checks it already does, this tool opens
every geometry file and checks the things only the line can tell you: that it has
points, that its `cum_m` is monotone and starts at zero, and that the segment's
stored `miles` is the line's own length. That closes the gap #16 recorded: a green
validator now does mean the geometry is sound.
"""
import json, os, sys, shutil, math

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'curate'))

import validate_graph as V
from inventory import M2MI

CURATION = os.path.join(ROOT, 'curation')
OUT = os.path.join(ROOT, 'public', 'data')
DISPLAY_EPS_DEG = 0.00008   # ~9 m; below the width of a rendered line at every zoom used
CHECK = '--check' in sys.argv


def rdp(pts, eps):
    """Douglas-Peucker on (lat, lon) pairs, eps in degrees. Screen use only."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        ax, ay, bx, by = pts[a][1], pts[a][0], pts[b][1], pts[b][0]
        dx, dy = bx - ax, by - ay
        n = math.hypot(dx, dy)
        best, bi = -1.0, -1
        for i in range(a + 1, b):
            px, py = pts[i][1], pts[i][0]
            d = abs(dy * px - dx * py + bx * ay - by * ax) / n if n else math.hypot(px - ax, py - ay)
            if d > best:
                best, bi = d, i
        if best > eps:
            keep[bi] = True
            stack += [(a, bi), (bi, b)]
    return [p for p, k in zip(pts, keep) if k]


def check_geometry(graph):
    """The line-level checks validate_graph.py cannot do without opening files."""
    for s in graph['segments']:
        path = os.path.join(CURATION, s['geometry'])
        if not os.path.exists(path):
            V.err(f"segment {s['id']!r} geometry file {s['geometry']} is missing")
            continue
        g = json.load(open(path))
        coords, cum = g.get('coordinates', []), g.get('cum_m', [])
        if len(coords) < 2:
            V.err(f"segment {s['id']!r} geometry has {len(coords)} point(s) -- zero-length")
            continue
        if len(cum) != len(coords) or cum[0] != 0 or any(b < a for a, b in zip(cum, cum[1:])):
            V.err(f"segment {s['id']!r} cum_m is not a monotone distance from 0 matching its points")
            continue
        miles = round(cum[-1] * M2MI, 2)
        if abs(miles - s['miles']) > 0.011:
            V.err(f"segment {s['id']!r} stores {s['miles']} mi but its line measures {miles} mi "
                  f"-- run tools/build_geometry.py")


def emit(graph, obs):
    display = {'version': 1, 'segments': {}}
    total_in = total_out = 0
    for s in graph['segments']:
        g = json.load(open(os.path.join(CURATION, s['geometry'])))
        pts = [(round(c[1], 5), round(c[0], 5)) for c in g['coordinates']]
        simp = rdp(pts, DISPLAY_EPS_DEG)
        total_in += len(pts); total_out += len(simp)
        display['segments'][s['id']] = [[la, lo] for la, lo in simp]

    files = {
        'graph.json': json.dumps(graph, indent=1, ensure_ascii=False) + '\n',
        'display.json': json.dumps(display, separators=(',', ':')) + '\n',
        'observations.json': json.dumps(obs, indent=1, ensure_ascii=False) + '\n',
    }
    for s in graph['segments']:
        files[s['geometry']] = open(os.path.join(CURATION, s['geometry'])).read()

    changed = []
    for rel, body in files.items():
        dst = os.path.join(OUT, rel)
        old = open(dst).read() if os.path.exists(dst) else None
        if old != body:
            changed.append(rel)
            if not CHECK:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                open(dst, 'w').write(body)
    # anything under public/data not produced this run is stale
    stale = []
    for dp, _, fns in os.walk(OUT):
        for fn in fns:
            rel = os.path.relpath(os.path.join(dp, fn), OUT)
            if rel not in files:
                stale.append(rel)
                if not CHECK:
                    os.remove(os.path.join(dp, fn))
    return changed, stale, total_in, total_out, sum(len(b) for b in files.values())


def main():
    graph = json.load(open(os.path.join(CURATION, 'graph.json')))
    obs_path = os.path.join(CURATION, 'observations.json')
    obs = json.load(open(obs_path))
    stats = V.check(graph, obs, obs_path)
    check_geometry(graph)
    for w in V.warnings:
        print(f"  warn  {w}")
    for e in V.errors:
        print(f"  ERROR {e}")
    if V.errors:
        sys.exit(f"\n{len(V.errors)} error(s); nothing written.")
    changed, stale, n_in, n_out, nbytes = emit(graph, obs)
    verb = 'would write' if CHECK else 'wrote'
    print(f"{stats['segments']} segments {stats['miles']} mi, {stats['observations']} observations; "
          f"display {n_in:,} -> {n_out:,} points; {nbytes/1024:.0f} KB total")
    print(f"{verb} {len(changed)} file(s), removed {len(stale)} stale" if changed or stale
          else "public/data is up to date")
    if CHECK and (changed or stale):
        sys.exit(1)


if __name__ == '__main__':
    main()
