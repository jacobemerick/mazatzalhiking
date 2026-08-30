#!/usr/bin/env python3
"""Corpus inventory for the Mazatzal GPX tracks (issue #4).

    ./tools/inventory.py <directory-of-gpx-files>

Reads tools/trips.csv for the trip manifest (dates and names, which 20 of the 25
source files do not carry themselves). Reports per-trip stats, a resolution
diagnostic, distinct-vs-repeat mileage, how far apart repeat traversals sit, and
per-file problems.

Regenerate docs/gpx-corpus-inventory.md from this rather than editing numbers by hand.
"""
import argparse, csv, glob, math, os, sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime

M2MI = 1 / 1609.344
M2FT = 3.28084
HERE = os.path.dirname(os.path.abspath(__file__))


def parse(path):
    """Yield (track_name, [(lat, lon, ele|None, time|None), ...]) per <trk>."""
    root = ET.parse(path).getroot()
    ns = root.tag[1:root.tag.index('}')] if root.tag.startswith('{') else ''
    q = (lambda t: f'{{{ns}}}{t}') if ns else (lambda t: t)
    for trk in root.iter(q('trk')):
        nm = trk.find(q('name'))
        pts = []
        for tp in trk.iter(q('trkpt')):
            ele, tm = tp.find(q('ele')), tp.find(q('time'))
            t = None
            if tm is not None and tm.text:
                try:
                    t = datetime.fromisoformat(tm.text.strip().replace('Z', '+00:00'))
                except ValueError:
                    pass
            pts.append((float(tp.get('lat')), float(tp.get('lon')),
                        float(ele.text) if ele is not None and ele.text else None, t))
        if pts:
            yield (nm.text if nm is not None and nm.text else os.path.basename(path)), pts


def hav(a, b):
    R = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def bearing(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    return math.degrees(math.atan2(math.sin(dl) * math.cos(p2),
        math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)))


def turn(a, b, c):
    return abs(((bearing(a, b) - bearing(b, c)) + 180) % 360 - 180)


def pct(v, p):
    return v[min(len(v) - 1, int(len(v) * p))] if v else 0.0


def gain(eles, threshold):
    """Elevation gain counting a rise only once it clears `threshold`, so GPS
    noise does not accumulate. See issue #12."""
    if not eles:
        return 0.0
    g, base = 0.0, eles[0]
    for v in eles[1:]:
        if v - base >= threshold:
            g, base = g + v - base, v
        elif v < base:
            base = v
    return g


def load(directory):
    manifest = {r['file']: r for r in csv.DictReader(open(os.path.join(HERE, 'trips.csv')))}
    trips, unlisted = [], []
    for f in sorted(glob.glob(os.path.join(directory, '*.gpx'))):
        b = os.path.basename(f)
        if b not in manifest:
            unlisted.append(b)
            continue
        segs = [p for _, p in parse(f)]
        pts = [q for s in segs for q in s]
        d = [hav(s[i][:2], s[i + 1][:2]) for s in segs for i in range(len(s) - 1)]
        trips.append(dict(file=b, date=manifest[b]['date'], name=manifest[b]['trip'],
                          source=manifest[b]['source'], segs=segs, pts=pts, d=d,
                          dist=sum(d), timed=bool(pts) and all(q[3] for q in pts)))
    trips.sort(key=lambda t: t['date'])
    return trips, unlisted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('directory')
    ap.add_argument('--tolerance', type=float, default=25.0,
                    help='metres; two trips within this are treated as the same ground')
    args = ap.parse_args()

    trips, unlisted = load(args.directory)
    if not trips:
        sys.exit(f'no manifest-listed .gpx files under {args.directory}')
    for b in unlisted:
        print(f'!! not in tools/trips.csv, skipped: {b}', file=sys.stderr)

    total = sum(t['dist'] for t in trips)

    print('=== TRIPS ===')
    print(f"{'date':<12}{'trip':<38}{'seg':>4}{'pts':>7}{'mi':>7}{'med m':>7}{'gain ft':>9}{'time':>6}")
    print('-' * 90)
    for t in trips:
        g = sum(gain([q[2] for q in s if q[2] is not None], 5) for s in t['segs'])
        print(f"{t['date']:<12}{t['name'][:37]:<38}{len(t['segs']):>4}{len(t['pts']):>7}"
              f"{t['dist'] * M2MI:>7.1f}{pct(sorted(t['d']), .5):>7.1f}{g * M2FT:>9,.0f}"
              f"{('yes' if t['timed'] else 'no'):>6}")
    print('-' * 90)
    print(f"{len(trips)} trips  {sum(len(t['segs']) for t in trips)} tracks  "
          f"{sum(len(t['pts']) for t in trips):,} points  {total * M2MI:.1f} mi  "
          f"{trips[0]['date']} to {trips[-1]['date']}")

    # ---- resolution ------------------------------------------------------
    alld = sorted(x for t in trips for x in t['d'])
    print('\n=== RESOLUTION ===')
    print('spacing m: ' + '  '.join(f'{k}={pct(alld, v):.1f}' for k, v in
          [('p10', .1), ('median', .5), ('p90', .9), ('p99', .99)]))
    print('\nspacing by curvature — tightening toward hairpins means the export is')
    print('shape-aware (Douglas-Peucker); flat means blind fixed-interval decimation:')
    buckets = defaultdict(list)
    for t in trips:
        for s in t['segs']:
            for i in range(1, len(s) - 1):
                a = turn(s[i - 1], s[i], s[i + 1])
                k = ('straight <10' if a < 10 else 'gentle 10-30' if a < 30
                     else 'curvy 30-60' if a < 60 else 'hairpin >60')
                buckets[k].append(hav(s[i][:2], s[i + 1][:2]))
    for k in ('straight <10', 'gentle 10-30', 'curvy 30-60', 'hairpin >60'):
        v = sorted(buckets[k])
        print(f'  {k:<16} n={len(v):<7} median {pct(v, .5):>5.1f} m')

    # ---- elevation -------------------------------------------------------
    eles = [q[2] for t in trips for q in t['pts'] if q[2] is not None]
    print('\n=== ELEVATION ===')
    print(f'range {min(eles):.0f}-{max(eles):.0f} m ({min(eles) * M2FT:,.0f}-{max(eles) * M2FT:,.0f} ft)')
    for th in (0, 3, 5, 10):
        g = sum(gain([q[2] for q in s if q[2] is not None], th)
                for t in trips for s in t['segs'])
        print(f"  {('naive' if th == 0 else f'{th} m threshold'):<16}{g * M2FT:>10,.0f} ft")

    # ---- distinct ground -------------------------------------------------
    print(f'\n=== DISTINCT VS REPEAT (@{args.tolerance:.0f} m) ===')
    cell = args.tolerance / 111320.0
    claimed, distinct = set(), 0.0
    contrib = []
    for t in trips:
        new = 0.0
        for s in t['segs']:
            for i in range(len(s) - 1):
                c = (round(s[i][0] / cell), round(s[i][1] / cell))
                if c not in claimed:
                    claimed.add(c)
                    new += hav(s[i][:2], s[i + 1][:2])
        distinct += new
        contrib.append((t, new))
    print(f'{distinct * M2MI:.1f} mi distinct of {total * M2MI:.1f} recorded '
          f'({distinct / total * 100:.0f}% distinct, {(1 - distinct / total) * 100:.0f}% repeat)')
    print('\nnew ground each trip added, chronologically:')
    for t, new in contrib:
        print(f"  {t['date']}  {t['name'][:36]:<38}{new * M2MI:>6.1f} new /{t['dist'] * M2MI:>6.1f} mi"
              f"  ({new / t['dist'] * 100:>3.0f}%)")

    # ---- separation between repeat traversals ----------------------------
    print('\n=== HOW FAR APART REPEAT TRAVERSALS SIT ===')
    CELL = 100 / 111320.0
    idx = defaultdict(list)
    for ti, t in enumerate(trips):
        for q in t['pts']:
            idx[(round(q[0] / CELL), round(q[1] / CELL))].append((ti, q))
    seps = []
    for a in range(len(trips)):
        for b in range(a + 1, len(trips)):
            pair = []
            for q in trips[a]['pts'][::3]:
                c = (round(q[0] / CELL), round(q[1] / CELL))
                best = 1e9
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for tj, r in idx.get((c[0] + dx, c[1] + dy), ()):
                            if tj == b:
                                best = min(best, hav(q[:2], r[:2]))
                if best <= 60.0:
                    pair.append(best)
            if len(pair) >= 50:
                seps += pair
    seps.sort()
    print('  ' + '  '.join(f'{k}={pct(seps, v):.1f}m' for k, v in
          [('median', .5), ('p75', .75), ('p90', .9), ('p95', .95), ('p99', .99)]))
    for th in (10, 20, 30):
        print(f'  within {th}m: {sum(1 for x in seps if x <= th) / len(seps) * 100:.0f}%')
    print('  -> sets the merge tolerance for #13')

    # ---- flags -----------------------------------------------------------
    print('\n=== FLAGS ===')
    for t in trips:
        msgs = []
        if not t['timed']:
            msgs.append('no timestamps')
        if pct(sorted(t['d']), .5) > 30:
            msgs.append(f"still decimated (median {pct(sorted(t['d']), .5):.1f} m)")
        big = [x for x in t['d'] if x > 250]
        if big:
            msgs.append(f'{len(big)} gap(s) >250m (max {max(big):.0f}m)')
        if len(t['segs']) > 1:
            msgs.append(f"{len(t['segs'])} tracks in one file")
        if msgs:
            print(f"  {t['name'][:36]:<38} {'; '.join(msgs)}")


if __name__ == '__main__':
    main()
