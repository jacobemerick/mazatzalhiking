#!/usr/bin/env python3
"""Ingest a new trip in one command (#51).

    ./tools/ingest_trip.py <gpx> <date> [--name "…"] [--triplog report.md] [--stub] [--dry-run]

After a hike the inputs are a GPX track, a date and, later, a written report. This
puts each where it lives and records the join between them:

1. copies the GPX into `archive/gpx/` as exported (a browser's ` (1)` suffix is
   dropped, per archive/README.md), refusing if that name is already archived
2. adds the trip to `tools/trips.csv`
3. works out which legs the track walked -- a leg counts when at least half of its
   line lies within 30 m of the track -- and adds a `curation/triplogs.json` entry,
   printing every leg's coverage so partial legs are visible
4. with `--triplog`, copies the report to `archive/haz/triplog/<date>.md`, turning
   bare section-title lines into `##` headings if it has none of its own
5. runs the geometry rebuild, which picks the track up as another pass on every leg
   it walked (#37), and reports the mileage delta and which legs' lines moved
6. prints, per trail file, the `## … {#id}` headings the trip touched in walking
   order; `--stub` puts an empty `### <date> ` under each leg's heading to fill in

Then `./tools/build.sh` as usual (a stub left empty fails it, on purpose).

Ground the track walks that is not in the graph is reported, never added: a new
trail needs the curation tool, and walked ground is not automatically trail (see
the excluded-ground decisions in docs/trail-graph-schema.md).

The report often comes later than the track. Running again with the same GPX and
`--triplog` does only step 4, provided the trip's entry has no report yet.

`--dry-run` prints everything, including the geometry delta, and writes nothing.
"""
import argparse, csv, json, math, os, re, shutil, sys
import xml.etree.ElementTree as ET
from datetime import timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)

from inventory import parse, hav, M2MI

GPX_DIR = os.path.join(ROOT, 'archive', 'gpx')
TRIPLOG_DIR = os.path.join(ROOT, 'archive', 'haz', 'triplog')
TRIPS = os.path.join(HERE, 'trips.csv')
TRIPLOGS = os.path.join(ROOT, 'curation', 'triplogs.json')
GRAPH = os.path.join(ROOT, 'curation', 'graph.json')
TRAILS_MD = os.path.join(ROOT, 'content', 'trails')

NEAR_M = 30.0          # a leg point this close to the track was walked
COUNT_AT = 0.5         # ...and a leg counts when this much of it was
SHOW_AT = 0.1          # coverage worth printing even though it does not count
MIN_RUN_M = 100.0      # shorter brushes with a leg (crossing it at a junction) are not visits
OFF_GRAPH_M = 400.0    # off-graph stretches shorter than this are wander, not ground
PARTIAL_BELOW = 0.9    # a counted leg below this coverage is called partial in the entry's note

COPY_SUFFIX = re.compile(r' \(\d+\)(?=\.gpx$)', re.I)
TARGET = re.compile(r'^##\s+.*\{#(?P<id>(?:node:)?[0-9A-Za-z]{2,4})\}\s*$')


# --- geometry in a flat local frame --------------------------------------------------

class Frame:
    def __init__(self, lat, lon):
        self.lat0, self.lon0 = lat, lon
        self.my = 111_132.0
        self.mx = 111_320.0 * math.cos(math.radians(lat))

    def xy(self, lat, lon):
        return ((lon - self.lon0) * self.mx, (lat - self.lat0) * self.my)


def seg_dist(p, a, b):
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


class Lines:
    """Grid index over the pieces of some polylines, for nearest-line queries."""
    CELL = 50.0

    def __init__(self, lines):
        self.grid = {}
        self.lines = lines
        for key, xy in lines.items():
            for i in range(len(xy) - 1):
                (ax, ay), (bx, by) = xy[i], xy[i + 1]
                for cx in range(int(min(ax, bx) // self.CELL) - 1, int(max(ax, bx) // self.CELL) + 2):
                    for cy in range(int(min(ay, by) // self.CELL) - 1, int(max(ay, by) // self.CELL) + 2):
                        self.grid.setdefault((cx, cy), set()).add((key, i))

    def nearest(self, p, within):
        """(distance, key) of the closest line within `within` metres, else (None, None)."""
        best = (None, None)
        for key, i in self.grid.get((int(p[0] // self.CELL), int(p[1] // self.CELL)), ()):
            xy = self.lines[key]
            d = seg_dist(p, xy[i], xy[i + 1])
            if d <= within and (best[0] is None or d < best[0]):
                best = (d, key)
        return best


def resample(xy, step):
    """Points every `step` metres along a polyline, each with the length it stands for."""
    out = []
    for i in range(len(xy) - 1):
        (ax, ay), (bx, by) = xy[i], xy[i + 1]
        L = math.hypot(bx - ax, by - ay)
        n = max(1, int(math.ceil(L / step)))
        for k in range(n):
            t = (k + 0.5) / n
            out.append(((ax + t * (bx - ax), ay + t * (by - ay)), L / n))
    return out


# --- what the track walked ------------------------------------------------------------

def walked(pts, graph):
    """Coverage of every leg, the order legs were visited in, and off-graph stretches."""
    frame = Frame(pts[len(pts) // 2][0], pts[len(pts) // 2][1])
    track = [frame.xy(p[0], p[1]) for p in pts]
    legs = {}
    for s in graph['segments']:
        g = json.load(open(os.path.join(ROOT, 'curation', s['geometry'])))
        legs[s['id']] = [frame.xy(c[1], c[0]) for c in g['coordinates']]

    tindex = Lines({'track': track})
    coverage = {}
    for sid, xy in legs.items():
        samples = resample(xy, 10.0)
        total = sum(w for _, w in samples)
        hit = sum(w for p, w in samples if tindex.nearest(p, NEAR_M)[0] is not None)
        if hit:
            coverage[sid] = hit / total

    # Each track point belongs to the nearest leg within reach, or to none. Runs of the
    # same label, with the short ones (brushing a leg at a junction) dropped, are visits.
    lindex = Lines(legs)
    step = [0.0] + [math.hypot(track[i][0] - track[i - 1][0], track[i][1] - track[i - 1][1])
                    for i in range(1, len(track))]
    runs = []
    for i, p in enumerate(track):
        _, sid = lindex.nearest(p, NEAR_M)
        if runs and runs[-1]['leg'] == sid:
            runs[-1]['m'] += step[i]
            runs[-1]['last'] = i
        else:
            runs.append(dict(leg=sid, m=step[i], first=i, last=i))
    visits = []
    for r in runs:
        if r['leg'] is None or r['m'] < MIN_RUN_M:
            continue
        if visits and visits[-1] == r['leg']:
            continue
        visits.append(r['leg'])

    # Off-graph: points with no leg in reach. Merge across short on-graph blips first,
    # so a bushwhack that crosses a trail is reported as one stretch, not two.
    off, cur = [], None
    for r in runs:
        if r['leg'] is None:
            if cur and r['first'] - cur['last'] <= 1:
                cur.update(last=r['last'], m=cur['m'] + r['m'])
            else:
                cur = dict(r)
                off.append(cur)
        elif cur and r['m'] < MIN_RUN_M:
            cur.update(last=r['last'], m=cur['m'] + r['m'])
        else:
            cur = None
    off = [o for o in off if o['m'] >= OFF_GRAPH_M]
    for o in off:
        o['left'] = next((r['leg'] for r in reversed(runs) if r['last'] < o['first']
                          and r['leg'] and r['m'] >= MIN_RUN_M), None)
        o['joined'] = next((r['leg'] for r in runs if r['first'] > o['last']
                            and r['leg'] and r['m'] >= MIN_RUN_M), None)
    return coverage, visits, off


def nearest_node(graph, lat, lon):
    return min(((hav((lat, lon), (n['lat'], n['lon'])), n) for n in graph['nodes']),
               key=lambda x: x[0])


# --- the files --------------------------------------------------------------------------

def gpx_meta(path):
    root = ET.parse(path).getroot()
    ns = root.tag[1:root.tag.index('}')] if root.tag.startswith('{') else ''
    q = (lambda t: f'{{{ns}}}{t}') if ns else (lambda t: t)
    name = root.find(f"{q('metadata')}/{q('name')}")
    if name is None:
        name = root.find(f"{q('trk')}/{q('name')}")
    return (root.get('creator') or ''), (name.text.strip() if name is not None and name.text else None)


def source_of(basename, creator):
    if 'traildex' in creator.lower() or basename.startswith('RS_'):
        return 'traildex'
    if re.match(r'^\d+_', basename):
        return 'hikearizona'
    return None


def format_triplog(text):
    """#40's form: per-section titles as `##` headings. A report that already has a
    heading is left exactly as written. Otherwise a short line standing alone between
    a blank line and a paragraph, with no sentence ending, is taken as a title."""
    lines = text.replace('\r\n', '\n').rstrip('\n').split('\n')
    if any(re.match(r'^#{1,6}\s', l) for l in lines):
        return '\n'.join(lines) + '\n', []
    promoted = []
    for i, l in enumerate(lines):
        s = l.strip()
        prev_blank = i == 0 or not lines[i - 1].strip()
        next_text = i + 1 < len(lines) and lines[i + 1].strip()
        if (s and prev_blank and next_text and len(s) <= 60
                and not re.search(r'[.!?:,;"\']$', s) and not s.startswith(('-', '*', '!['))):
            lines[i] = '## ' + s
            promoted.append(s)
    return '\n'.join(lines) + '\n', promoted


def trail_sections():
    """{'segment-or-node id': (slug, heading line)} from content/trails/."""
    out = {}
    for fn in sorted(os.listdir(TRAILS_MD)):
        if fn.endswith('.md') and not fn.startswith('_'):
            for line in open(os.path.join(TRAILS_MD, fn)):
                m = TARGET.match(line.rstrip())
                if m:
                    out.setdefault(m.group('id'), (fn[:-3], line.rstrip()))
    return out


def stub(slug, sids, date):
    """Insert `### <date> ` straight under each leg heading (notes run newest-first)."""
    path = os.path.join(TRAILS_MD, slug + '.md')
    lines = open(path).read().split('\n')
    out, added = [], 0
    for i, line in enumerate(lines):
        out.append(line)
        m = TARGET.match(line)
        if m and m.group('id') in sids:
            rest = [l for l in lines[i + 1:i + 4] if l.strip()]
            if rest and rest[0].startswith(f'### {date}'):
                continue
            out += ['', f'### {date} ']
            added += 1
    with open(path, 'w') as f:
        f.write('\n'.join(out))
    return added


def write_json(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=1)
        f.write('\n')
    os.replace(tmp, path)


# --- the command ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('gpx')
    ap.add_argument('date', help='the day walked, YYYY-MM-DD (the day it started, for an overnight)')
    ap.add_argument('--name', help="trip name for trips.csv (default: the GPX's own name)")
    ap.add_argument('--source', help='exporter, for trips.csv (default: from the file)')
    ap.add_argument('--triplog', help='the written report, as markdown')
    ap.add_argument('--stub', action='store_true', help='add an empty dated note under each walked leg')
    ap.add_argument('--dry-run', action='store_true', help='print everything, write nothing')
    a = ap.parse_args()
    dry = a.dry_run
    say = print

    if not re.fullmatch(r'\d{4}-\d\d-\d\d', a.date):
        sys.exit(f'date must be YYYY-MM-DD, not {a.date!r}')
    if not os.path.isfile(a.gpx):
        sys.exit(f'no such file: {a.gpx}')
    if a.triplog and not os.path.isfile(a.triplog):
        sys.exit(f'no such file: {a.triplog}')

    base = COPY_SUFFIX.sub('', os.path.basename(a.gpx))
    dest = os.path.join(GPX_DIR, base)
    triplogs = json.load(open(TRIPLOGS))
    graph = json.load(open(GRAPH))
    nodes = {n['id']: n for n in graph['nodes']}
    segs = {s['id']: s for s in graph['segments']}
    log_rel = f'triplog/{a.date}.md'
    log_path = os.path.join(TRIPLOG_DIR, f'{a.date}.md')

    # A report arriving after its track: only step 4 is left to do.
    if os.path.exists(dest):
        entry = next((t for t in triplogs['triplogs'] if t.get('gpx') == base), None)
        if not (a.triplog and entry and entry.get('file') is None and entry['date'] == a.date):
            sys.exit(f'refusing: archive/gpx/{base} already exists (this trip is already ingested)')
        if os.path.exists(log_path):
            sys.exit(f'refusing: archive/haz/{log_rel} already exists')
        text, promoted = format_triplog(open(a.triplog).read())
        report_headings(promoted, text)
        if not dry:
            with open(log_path, 'w') as f:
                f.write(text)
            entry['file'] = log_rel
            write_json(TRIPLOGS, triplogs)
        say(f"\n{'would add' if dry else 'added'} the report to the {a.date} trip: archive/haz/{log_rel}")
        return

    rows = list(csv.DictReader(open(TRIPS)))
    if any(r['file'] == base for r in rows):
        sys.exit(f'refusing: {base} is already in tools/trips.csv')
    if a.triplog and os.path.exists(log_path):
        sys.exit(f'refusing: archive/haz/{log_rel} already exists')
    if any(t['date'] == a.date for t in triplogs['triplogs']):
        sys.exit(f'refusing: curation/triplogs.json already has a trip on {a.date}')

    creator, gpx_name = gpx_meta(a.gpx)
    name = a.name or gpx_name
    source = a.source or source_of(base, creator)
    if not name:
        sys.exit('the GPX carries no name; pass --name')
    if not source:
        sys.exit(f'cannot tell which exporter wrote {base}; pass --source')

    segments = [p for _, p in parse(a.gpx)]
    pts = [p for s in segments for p in s]
    if not pts:
        sys.exit(f'{a.gpx} has no track points')
    miles = sum(hav(s[i][:2], s[i + 1][:2]) for s in segments for i in range(len(s) - 1)) * M2MI
    times = [p[3] for p in pts if p[3]]
    say(f'{base}: {name}, {miles:.1f} mi, {len(pts):,} points, {source}')
    if times:
        # Arizona keeps MST all year, so local is always UTC-7.
        local = (times[0] - timedelta(hours=7)).date().isoformat()
        if local != a.date:
            say(f'  note: the track starts on {local} (Arizona time), not {a.date}; check the date')

    # Step 3 is computed first: a track that walked no leg is probably the wrong file,
    # and nothing should be written for it.
    coverage, visits, off = walked(pts, graph)
    counted = []
    for s in visits:
        if coverage.get(s, 0) >= COUNT_AT and s not in counted:
            counted.append(s)
    counted += sorted(s for s, c in coverage.items() if c >= COUNT_AT and s not in counted)
    if not counted:
        best = max(coverage.items(), key=lambda x: x[1], default=(None, 0))
        sys.exit(f'refusing: the track walks no leg of the graph (best is {best[0]} at '
                 f'{best[1]:.0%}); is this the right file?')

    say(f'\nlegs walked (counted at >= {COUNT_AT:.0%} of the line within {NEAR_M:.0f} m), in walking order:')
    for sid in counted:
        say(f'  {sid}  {coverage[sid]:4.0%}  {segs[sid]["miles"]:5.2f} mi  {segs[sid]["name"]}')
    say('  visits: ' + ' '.join(visits))
    partial = sorted((s for s, c in coverage.items() if SHOW_AT <= c < COUNT_AT), key=lambda s: -coverage[s])
    if partial:
        say('touched but not counted:')
        for sid in partial:
            say(f'  {sid}  {coverage[sid]:4.0%}  {segs[sid]["miles"]:5.2f} mi  {segs[sid]["name"]}')
    if off:
        say('\nwalked off the graph (reported, not added -- new trail needs the curation tool):')
        for o in off:
            ends = []
            for leg, i, verb in ((o['left'], o['first'], 'leaves'), (o['joined'], o['last'], 'rejoins')):
                d, n = nearest_node(graph, *pts[i][:2])
                ends.append(f'{verb} {leg}' if leg else f'{verb} nothing ({d:,.0f} m from {n["name"]})')
            say(f"  {o['m'] * M2MI:4.1f} mi  {', '.join(ends)}  [track points {o['first']}-{o['last']}]")

    entry = dict(file=log_rel if a.triplog else None, date=a.date, gpx=base, basis='gpx',
                 segments=counted)
    notes = []
    part = [s for s in counted if coverage[s] < PARTIAL_BELOW]
    if part:
        notes.append('Partial: ' + ', '.join(f'{s} ({coverage[s]:.0%})' for s in part) + '.')
    if partial:
        notes.append('Touched, not counted: ' + ', '.join(f'{s} ({coverage[s]:.0%})' for s in partial) + '.')
    if notes:
        entry['note'] = ' '.join(notes)

    # Steps 1, 2, 4.
    say(f"\n{'would copy' if dry else 'copied'} {os.path.basename(a.gpx)} -> archive/gpx/{base}")
    say(f"{'would add' if dry else 'added'} tools/trips.csv row: {base},{a.date},{name},{source}")
    say(f"{'would add' if dry else 'added'} curation/triplogs.json entry: {json.dumps(entry)}")
    if a.triplog:
        text, promoted = format_triplog(open(a.triplog).read())
        report_headings(promoted, text)
        say(f"{'would copy' if dry else 'copied'} the report -> archive/haz/{log_rel}")
    if not dry:
        shutil.copyfile(a.gpx, dest)
        rows.append(dict(file=base, date=a.date, trip=name, source=source))
        rows.sort(key=lambda r: r['file'])
        with open(TRIPS, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['file', 'date', 'trip', 'source'], lineterminator='\n')
            w.writeheader()
            w.writerows(rows)
        triplogs['triplogs'].append(entry)
        triplogs['triplogs'].sort(key=lambda t: t['date'])
        write_json(TRIPLOGS, triplogs)
        if a.triplog:
            with open(log_path, 'w') as f:
                f.write(text)

    # Step 5. A dry run hands the track to the rebuild in memory instead.
    say('\nrebuilding geometry...')
    import build_geometry as B
    extra = []
    if dry:
        extra = [dict(file=base, date=a.date, segs=segments)]
    r = B.rebuild(dry=dry, extra=extra, save_dem=not dry)
    b, f_ = r['before']['miles'], r['after']['miles']
    say(f'\nnetwork {b:.1f} -> {f_:.1f} mi ({f_ - b:+.2f}), '
        f"gain {r['before']['gain']:,} -> {r['after']['gain']:,} ft")
    if r['changes']:
        say("legs whose line moved (the new track now votes on them):")
        for sid, c in sorted(r['changes'].items()):
            mine = any(p.startswith(base + '#') for p in c['passes'])
            say(f"  {sid}  {c['miles'][0]:5.2f} -> {c['miles'][1]:5.2f} mi  "
                f"max shift {c['max_shift_m']:.1f} m{'' if mine else '  (not voted by this track)'}  {c['name']}")
    else:
        say('no leg line moved')

    # Step 6. Places passed between two legs in a row are listed too, where a file
    # already has a section for them.
    sections = trail_sections()
    order = []
    for i, sid in enumerate(visits):
        if i:
            shared = {segs[visits[i - 1]]['from'], segs[visits[i - 1]]['to']} & {segs[sid]['from'], segs[sid]['to']}
            order += [f'node:{n}' for n in sorted(shared)]
        if sid in counted:
            order.append(sid)
    by_file = {}
    for key in order:
        if key in sections:
            slug, heading = sections[key]
            if heading not in by_file.setdefault(slug, []):
                by_file[slug].append(heading)
    missing = [s for s in counted if s not in sections]
    say('\nwhere the notes go, per trail file in walking order:')
    for slug, heads in by_file.items():
        say(f'  content/trails/{slug}.md')
        for h in heads:
            say(f'    {h}')
    if missing:
        say(f"  legs with no section in any trail file (run tools/sync_trails.py): {', '.join(missing)}")
    if a.stub:
        for slug in by_file:
            sids = {k for k in counted if k in sections and sections[k][0] == slug}
            if dry:
                say(f'would stub {len(sids)} leg(s) in {slug}.md')
            else:
                say(f'stubbed {stub(slug, sids, a.date)} leg(s) in {slug}.md')

    say('\n--dry-run: nothing written' if dry else '\nnext: write the notes, then ./tools/build.sh')


def report_headings(promoted, text):
    if promoted:
        print(f'report: {len(promoted)} section title(s) made ## headings: ' + ' | '.join(promoted))
    elif not re.search(r'^#{1,6}\s', text, re.M):
        print('report: no section titles found; copied as written')


if __name__ == '__main__':
    main()
