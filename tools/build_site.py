#!/usr/bin/env python3
"""Emit the data the site is built from (#16, #18, #30).

    ./tools/build_site.py           # validate, then write static/data/ and data/
    ./tools/build_site.py --check   # validate only, write nothing

Reads the authored graph under `curation/` and the authored condition notes under
`content/trails/`, and writes two derived sets, both gitignored and rebuilt on every
deploy by tools/build.sh:

    static/data/   what the browser fetches -- the builder's graph, display lines,
                   per-segment geometry and observations (Hugo copies it to public/data/)
    data/          what the Hugo templates read -- trails with their legs in walking
                   order and figures for that direction, nodes by id, and observations
                   grouped by target, newest first

Nothing here is authored, and nothing is served from `curation/` or `content/`
directly.

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

`validate_graph.py` runs first and any error aborts the build, so a broken graph or
a malformed note cannot ship quietly. On top of the topology checks it already does, this tool opens
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
import observations as O
from inventory import M2MI
from trails import order_legs, leg_figures
from datetime import date

CURATION = os.path.join(ROOT, 'curation')
OUT = os.path.join(ROOT, 'static', 'data')
DATA = os.path.join(ROOT, 'data')
CONTENT = os.path.join(ROOT, 'content', 'trails')
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


def fmt_date(iso):
    d = date.fromisoformat(iso)
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def load_observations():
    """Every note in content/trails/, plus the trail each file belongs to."""
    obs = []
    slugs = {}
    for slug, (intro, notes) in O.load_dir(CONTENT).items():
        obs.extend(notes)
        slugs[slug] = intro
    return {'version': 1, 'observations': obs}, slugs


def trails_data(graph, nodes):
    """Per-trail: legs in walking order with figures for that direction, totals, the
    builder route string, endpoints, and the recorded-date sentence."""
    out = {}
    for t in graph['trails']:
        legs = order_legs(t['id'], graph['segments'], nodes)
        if not legs:
            V.warn(f"trail {t['id']!r} ({t['name']!r}) has no legs")
            continue
        rows = []
        for s, rev in legs:
            a, b, gain, loss = leg_figures(s, rev)
            rows.append(dict(id=s['id'], name=s['name'], from_=nodes[a]['name'], to=nodes[b]['name'],
                             miles=s['miles'], gain_ft=gain, loss_ft=loss, loop=s['from'] == s['to']))
        # Hugo templates can't read a key called `from_`; name it plainly.
        for r in rows:
            r['from'] = r.pop('from_')
        dates = sorted({src['date'] for s, _ in legs for src in s['sources']})
        recorded = (f"recorded on {fmt_date(dates[0])}" if len(dates) == 1 else
                    f"recorded on {len(dates)} trips between {fmt_date(dates[0])} and {fmt_date(dates[-1])}")
        out[t['id']] = dict(
            id=t['id'], name=t['name'], slug=t['slug'], kind=t['kind'], code=t.get('code'),
            legs=rows, miles=sum(r['miles'] for r in rows),
            gain_ft=sum(r['gain_ft'] for r in rows), loss_ft=sum(r['loss_ft'] for r in rows),
            first=rows[0]['from'], last=rows[-1]['to'],
            route='.'.join(('-' if r else '') + s['id'] for s, r in legs),
            recorded=recorded)
    return out


def conditions_data(obs):
    """observations grouped by target, newest first, ties in file order -- the same
    ordering conditions.js index() applies."""
    by = {}
    for i, o in enumerate(obs['observations']):
        by.setdefault(o['target'], []).append((o['date'], -i, o))
    return {k: [o for _, _, o in sorted(v, key=lambda x: (x[0], x[1]), reverse=True)] for k, v in by.items()}


def emit(graph, obs):
    display = {'version': 1, 'segments': {}}
    total_in = total_out = 0
    for s in graph['segments']:
        g = json.load(open(os.path.join(CURATION, s['geometry'])))
        pts = [(round(c[1], 5), round(c[0], 5)) for c in g['coordinates']]
        simp = rdp(pts, DISPLAY_EPS_DEG)
        total_in += len(pts); total_out += len(simp)
        display['segments'][s['id']] = [[la, lo] for la, lo in simp]

    nodes = {n['id']: n for n in graph['nodes']}
    files = {
        os.path.join(OUT, 'graph.json'): json.dumps(graph, indent=1, ensure_ascii=False) + '\n',
        os.path.join(OUT, 'display.json'): json.dumps(display, separators=(',', ':')) + '\n',
        os.path.join(OUT, 'observations.json'): json.dumps(obs, indent=1, ensure_ascii=False) + '\n',
        os.path.join(DATA, 'trails.json'): json.dumps(trails_data(graph, nodes), indent=1, ensure_ascii=False) + '\n',
        os.path.join(DATA, 'nodes.json'): json.dumps(nodes, indent=1, ensure_ascii=False) + '\n',
        os.path.join(DATA, 'conditions.json'): json.dumps(conditions_data(obs), indent=1, ensure_ascii=False) + '\n',
    }
    for s in graph['segments']:
        files[os.path.join(OUT, s['geometry'])] = open(os.path.join(CURATION, s['geometry'])).read()

    changed = []
    for dst, body in files.items():
        old = open(dst).read() if os.path.exists(dst) else None
        if old != body:
            changed.append(os.path.relpath(dst, ROOT))
            if not CHECK:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                open(dst, 'w').write(body)
    stale = []
    for base in (OUT, DATA):
        for dp, _, fns in os.walk(base):
            for fn in fns:
                full = os.path.join(dp, fn)
                if full not in files:
                    stale.append(os.path.relpath(full, ROOT))
                    if not CHECK:
                        os.remove(full)
    return changed, stale, total_in, total_out, sum(len(b) for b in files.values())


def main():
    graph = json.load(open(os.path.join(CURATION, 'graph.json')))
    try:
        obs, _ = load_observations()
    except O.ParseError as e:
        sys.exit(f"  ERROR {e}")
    stats = V.check(graph, obs, os.path.join(CONTENT, 'observations'))
    check_geometry(graph)
    # every trail file must belong to a trail, and every trail must have a file
    slugs = {t['slug'] for t in graph['trails']}
    have = {fn[:-3] for fn in os.listdir(CONTENT) if fn.endswith('.md') and not fn.startswith('_')}
    for s in sorted(have - slugs):
        V.err(f"content/trails/{s}.md is not a trail in the graph")
    for s in sorted(slugs - have):
        V.err(f"trail {s!r} has no content/trails/{s}.md -- run tools/sync_trails.py")
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
          else "static/data and data are up to date")
    if CHECK and (changed or stale):
        sys.exit(1)


if __name__ == '__main__':
    main()
