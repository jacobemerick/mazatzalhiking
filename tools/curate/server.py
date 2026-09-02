#!/usr/bin/env python3
"""Local junction curation tool (#14).

    ./tools/curate/server.py            # then open http://localhost:8723

Local authoring only. This does not ship with the site and has no bearing on the
deployed Worker, which still serves nothing but public/.

Reads the recorded corpus from archive/gpx and writes curated nodes and segments to
curation/graph.json in the schema from docs/trail-graph-schema.md.

Why this can run before #10/#11/#13 land: node coordinates are authored truth and
segment geometry is derived, so junctions placed against raw tracks stay correct when
cleaning and traversal-merging later change the lines underneath. Only the derived
geometry is recomputed.

The browser holds a display-simplified copy of the corpus; full resolution stays here,
so snapping and tracing are done server-side against the real points.
"""
import http.server, json, math, os, socketserver, sys, urllib.parse
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from inventory import load, hav, M2MI, M2FT

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
HERE = os.path.dirname(os.path.abspath(__file__))
GPX = os.path.join(ROOT, 'archive', 'gpx')
OUT = os.path.join(ROOT, 'curation', 'graph.json')
PORT = 8723

# ---------------------------------------------------------------- corpus ----

TRACKS = []   # {key, trip, date, file, pts:[(lat,lon,ele)], cum:[m]}


def build_corpus():
    trips, _ = load(GPX)
    for t in trips:
        for si, seg in enumerate(t['segs']):
            pts = [(p[0], p[1], p[2]) for p in seg]
            cum = [0.0]
            for i in range(len(pts) - 1):
                cum.append(cum[-1] + hav(pts[i][:2], pts[i+1][:2]))
            TRACKS.append(dict(key=f"{t['file']}#{si}", trip=t['name'], date=t['date'],
                               file=t['file'], pts=pts, cum=cum))
    total = sum(t['cum'][-1] for t in TRACKS) * M2MI
    print(f'corpus: {len(TRACKS)} tracks, {sum(len(t["pts"]) for t in TRACKS):,} points, {total:.1f} mi')


def rdp(pts, eps):
    """Douglas-Peucker on (lat,lon,...) tuples, eps in degrees-ish. Display only."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        ax, ay = pts[a][1], pts[a][0]
        bx, by = pts[b][1], pts[b][0]
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


def corpus_geojson():
    feats = []
    for t in TRACKS:
        simp = rdp(t['pts'], 0.00008)   # ~9 m
        feats.append({
            'type': 'Feature',
            'properties': {'key': t['key'], 'trip': t['trip'], 'date': t['date'],
                           'file': t['file'], 'miles': round(t['cum'][-1] * M2MI, 2)},
            'geometry': {'type': 'LineString',
                         'coordinates': [[round(p[1], 6), round(p[0], 6)] for p in simp]},
        })
    return {'type': 'FeatureCollection', 'features': feats}


# ----------------------------------------------------------- snap / trace ----

def snap(lat, lon, limit=60.0):
    """Nearest point on any track. Junctions belong on the tread, not beside it."""
    best = None
    for t in TRACKS:
        for i, p in enumerate(t['pts']):
            d = hav((lat, lon), p[:2])
            if best is None or d < best['dist']:
                best = dict(dist=d, key=t['key'], index=i, lat=p[0], lon=p[1],
                            ele=p[2], trip=t['trip'], date=t['date'])
    if best and best['dist'] <= limit:
        best['ele_ft'] = round(best['ele'] * M2FT) if best['ele'] is not None else None
        return best
    return None


def passes_through(t, lat, lon, tol=40.0):
    """Every distinct approach of one track to a point, not just its closest.

    A loop or an out-and-back comes near the same junction more than once, and
    each visit is a separate place the tread could be cut. Collapsing them to the
    single nearest one is what let a segment silently trace the long way round:
    two endpoints landed on different visits and the sub-path between them ran
    most of the way round the loop. Consecutive points inside tol are one visit,
    represented by the nearest of them."""
    ds = [hav((lat, lon), p[:2]) for p in t['pts']]
    out, i, n = [], 0, len(ds)
    while i < n:
        if ds[i] > tol:
            i += 1
            continue
        j = i
        while j < n and ds[j] <= tol:
            j += 1
        k = min(range(i, j), key=lambda x: ds[x])
        out.append((k, ds[k]))
        i = j
    return out


def tracks_through(lat, lon, tol=40.0):
    """Which recorded tracks pass within tol of this point, and where. One entry
    per visit, so a track that doubles back through a junction is listed twice --
    which is itself the tell that the junction sits on a loop or an out-and-back."""
    out = []
    for t in TRACKS:
        for i, d in passes_through(t, lat, lon, tol):
            out.append(dict(key=t['key'], index=i, dist=round(d, 1),
                            trip=t['trip'], date=t['date']))
    return sorted(out, key=lambda x: x['dist'])


MIN_ARC_M = 10.0


def arcs(alat, alon, blat, blon, tol=40.0, limit=12):
    """Every sub-path of a single recorded track running between two points.

    Either endpoint can fall on more than one visit, so pairing them is a cross
    product rather than a lookup, and each pair is a genuinely different way
    round. Shortest first: where one track offers two arcs between the same pair,
    the short one is the leg and the long one is the rest of the loop.

    Arcs within a short way of the shortest are all the same leg recorded on
    different trips, where length says nothing -- so inside that band the
    tightest snap wins, which is the older behaviour and still the right one.
    The caller gets the whole list either way, because the point is to make the
    choice visible rather than to guess well silently."""
    out = []
    for t in TRACKS:
        pa = passes_through(t, alat, alon, tol)
        if not pa:
            continue
        pb = passes_through(t, blat, blon, tol)
        for ia, da in pa:
            for ib, db in pb:
                metres = abs(t['cum'][ib] - t['cum'][ia])
                if metres < MIN_ARC_M:
                    continue
                out.append(dict(key=t['key'], trip=t['trip'], date=t['date'],
                                i0=ia, i1=ib, miles=round(metres * M2MI, 2),
                                off_m=round(da + db)))
    out.sort(key=lambda x: (x['miles'], x['off_m']))
    if out:
        band = out[0]['miles'] + max(0.05, out[0]['miles'] * 0.1)
        same = sorted((x for x in out if x['miles'] <= band), key=lambda x: (x['off_m'], x['miles']))
        out = same + [x for x in out if x['miles'] > band]
    return out[:limit]


def profile_gain_loss(eles, threshold_m=5.0):
    """Gain and loss with the direction-symmetric algorithm the schema prescribes:
    simplify the elevation profile first, then sum. Reversing the input swaps the
    two results exactly, which is what lets a segment store one pair of numbers."""
    e = [x for x in eles if x is not None]
    if len(e) < 2:
        return 0.0, 0.0
    ext = [e[0]]
    for v in e[1:]:
        if len(ext) < 2:
            if v != ext[-1]:
                ext.append(v)
            continue
        up_prev = ext[-1] > ext[-2]
        up_now = v > ext[-1]
        if v == ext[-1]:
            continue
        if up_now == up_prev:
            ext[-1] = v            # extend the run
        else:
            ext.append(v)          # direction changed
    while len(ext) > 2:
        runs = [(abs(ext[i+1] - ext[i]), i) for i in range(len(ext) - 1)]
        interior = [(m, i) for m, i in runs if 0 < i < len(ext) - 2]
        if not interior:
            break
        m, i = min(interior)
        if m >= threshold_m:
            break
        del ext[i:i+2]             # drop the reversal, neighbours merge
        merged = [ext[0]]
        for v in ext[1:]:
            if len(merged) >= 2 and (v > merged[-1]) == (merged[-1] > merged[-2]):
                merged[-1] = v
            elif v != merged[-1]:
                merged.append(v)
        ext = merged
    gain = sum(max(0.0, ext[i+1] - ext[i]) for i in range(len(ext) - 1))
    loss = sum(max(0.0, ext[i] - ext[i+1]) for i in range(len(ext) - 1))
    return gain, loss


def trace(key, i0, i1):
    """Sub-path of one recorded track between two snapped indices."""
    t = next((x for x in TRACKS if x['key'] == key), None)
    if t is None:
        return None
    a, b = (i0, i1) if i0 <= i1 else (i1, i0)
    pts = t['pts'][a:b+1]
    if len(pts) < 2:
        return None
    metres = t['cum'][b] - t['cum'][a]
    gain, loss = profile_gain_loss([p[2] for p in pts])
    if i0 > i1:
        pts = pts[::-1]
        gain, loss = loss, gain
    return dict(coordinates=[[round(p[1], 6), round(p[0], 6)] for p in rdp(pts, 0.00003)],
                miles=round(metres * M2MI, 2),
                gain_ft=round(gain * M2FT), loss_ft=round(loss * M2FT),
                source=dict(file=t['file'], date=t['date']))


# ------------------------------------------------------------------ state ----

EMPTY = {'version': 1, 'trails': [], 'nodes': [], 'segments': [], 'features': [], 'retired': []}


GEO = os.path.join(os.path.dirname(OUT), 'geometry')


def read_state():
    """Load the curated graph, re-attaching each segment's geometry for display.

    Geometry lives in its own file per segment, exactly as the schema requires, so
    graph.json stays small and schema-valid. The browser needs the points to draw, so
    they are attached under a leading-underscore key that write_state strips again."""
    if not os.path.exists(OUT):
        return json.loads(json.dumps(EMPTY))
    state = json.load(open(OUT))
    for seg in state.get('segments', []):
        f = os.path.join(GEO, f"{seg['id']}.json")
        if os.path.exists(f):
            seg['_geo'] = json.load(open(f))['coordinates']
    return state


def write_state(state):
    """Persist atomically. An interrupted save must never truncate a curation sitting."""
    os.makedirs(GEO, exist_ok=True)
    state = json.loads(json.dumps(state))
    seen = {}
    for seg in state.get('segments', []):
        # Refuse to write rather than let one segment's line overwrite another's on a
        # case-insensitive filesystem. mint() prevents this; this catches hand-edits.
        if seg['id'].lower() in seen:
            raise ValueError(f"segment ids {seen[seg['id'].lower()]!r} and {seg['id']!r} "
                             f"differ only by case and share one geometry file")
        seen[seg['id'].lower()] = seg['id']
    for seg in state.get('segments', []):
        geo = seg.pop('_geo', None)
        if geo is not None:
            gp = os.path.join(GEO, f"{seg['id']}.json")
            tmp = gp + '.tmp'
            with open(tmp, 'w') as f:
                json.dump({'type': 'LineString', 'coordinates': geo}, f)
            os.replace(tmp, gp)
        seg['geometry'] = f"geometry/{seg['id']}.json"
    tmp = OUT + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(state, f, indent=2)
        f.write('\n')
    os.replace(tmp, OUT)


ALPHABET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'


def mint(state, kind):
    """Next free code. Ids are allocated, never derived, and retired ids are never
    reissued -- see decision 1 in docs/trail-graph-schema.md.

    Ids must also differ by more than case. The schema's alphabet is case-sensitive
    base62, but a segment's geometry is one file per id, and macOS (APFS) and Windows
    are case-insensitive: minting `0a` alongside `0A` makes both resolve to the same
    path, and the second write silently destroys the first. So uniqueness is tested
    case-folded, which costs the lowercase half of the space (1,296 two-character ids
    remain, still clear of the ~850 upper bound in the schema doc) and buys back a
    class of data loss that nothing downstream can detect."""
    used = {x['id'].lower() for x in state.get(kind, [])}
    if kind == 'segments':
        used |= {r['id'].lower() for r in state.get('retired', [])}
    for a in ALPHABET:
        for b in ALPHABET:
            c = a + b
            if c.lower() not in used:
                return c
    raise RuntimeError('id space exhausted')


# ----------------------------------------------------------------- server ----

class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path in ('/', '/index.html'):
            body = open(os.path.join(HERE, 'index.html'), 'rb').read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif u.path == '/api/corpus':
            self._send(corpus_geojson())
        elif u.path == '/api/graph':
            self._send(read_state())
        elif u.path == '/api/snap':
            self._send(snap(float(q['lat'][0]), float(q['lon'][0])) or {})
        elif u.path == '/api/through':
            self._send(tracks_through(float(q['lat'][0]), float(q['lon'][0])))
        elif u.path == '/api/arcs':
            self._send(arcs(float(q['alat'][0]), float(q['alon'][0]),
                            float(q['blat'][0]), float(q['blon'][0])))
        elif u.path == '/api/trace':
            r = trace(q['key'][0], int(q['i0'][0]), int(q['i1'][0]))
            self._send(r or {}, 200 if r else 404)
        else:
            self._send({'error': 'not found'}, 404)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        n = int(self.headers.get('Content-Length', 0))
        payload = json.loads(self.rfile.read(n) or b'{}')
        state = read_state()

        if u.path == '/api/graph':
            write_state(payload)
            self._send({'ok': True})
        elif u.path == '/api/mint':
            self._send({'id': mint(state, payload['kind'])})
        else:
            self._send({'error': 'not found'}, 404)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == '__main__':
    build_corpus()
    s = read_state()
    print(f'curation: {len(s["nodes"])} nodes, {len(s["segments"])} segments  ->  '
          f'{os.path.relpath(OUT, ROOT)}')
    print(f'\n  http://localhost:{PORT}\n')
    try:
        Server(('127.0.0.1', PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print('stopped')
