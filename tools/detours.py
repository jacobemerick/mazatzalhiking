#!/usr/bin/env python3
"""Find where a leg doubles back on itself, and lay the candidates out for review (#38).

    ./tools/detours.py                    # list candidates
    ./tools/detours.py --sheet out.html   # also write a review sheet, one map per candidate

A detour is walked ground that is not the trail: a wander at a seep, a side trip to
an overlook. Geometrically it looks like a loop -- the line leaves itself and comes
back close by -- and so does a switchback, which is the trail. No rule separates
them (retrace tightness and repeat-visit consensus were both tested and both fail,
see docs/track-cleaning.md), so this tool does not decide. It finds every place a
leg comes back within `gap_m` of itself after `min_m`..`max_m` of walking, scores
each by how much of the loop retraces itself (a spur out-and-back retraces; a
switchback diverges), and writes a sheet with each candidate drawn over aerial
imagery, likeliest detours first. A person marks the real ones, and each becomes a
`skip` entry on the leg's arc in its geometry file.

Indices reported are into the recorded archive track, which is what `skip` takes.
"""
import json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
from inventory import load, hav, M2MI
import clean as C

GPX = os.path.join(ROOT, 'archive', 'gpx')
GRAPH = os.path.join(ROOT, 'curation', 'graph.json')
GEOM = os.path.join(ROOT, 'curation', 'geometry')

GAP_M, MIN_M, MAX_M = 12.0, 40.0, 400.0
RETRACE_M = 10.0


def candidates(pts, cum):
    """(i, j, loop_m, gap_m, retrace) for every self-return, coalesced so overlapping
    hits report the widest loop."""
    hits = []
    for i in range(len(pts)):
        for j in range(i + 2, len(pts)):
            along = cum[j] - cum[i]
            if along < MIN_M:
                continue
            if along > MAX_M:
                break
            d = hav(pts[i][:2], pts[j][:2])
            if d < GAP_M:
                hits.append((i, j, along, d))
    out = []
    for h in sorted(hits):
        if out and h[0] <= out[-1][1]:
            if h[2] > out[-1][2]:
                out[-1] = h
        else:
            out.append(h)
    scored = []
    for i, j, along, d in out:
        loop = pts[i:j + 1]
        # fraction of loop points with another loop point >= 25 m away along the
        # line but within RETRACE_M of it in space: a spur retraces, a switchback doesn't
        n = 0
        for a in range(len(loop)):
            for b in range(a + 1, len(loop)):
                if cum[i + b] - cum[i + a] < 25:
                    continue
                if hav(loop[a][:2], loop[b][:2]) <= RETRACE_M:
                    n += 1
                    break
        scored.append(dict(i=i, j=j, loop_m=round(along), gap_m=round(d, 1),
                           retrace=round(n / max(1, len(loop)), 2)))
    return scored


def main():
    sheet = None
    if '--sheet' in sys.argv:
        sheet = sys.argv[sys.argv.index('--sheet') + 1]
    trips, _ = load(GPX)
    tracks = {}
    for t in trips:
        for si, seg in enumerate(t['segs']):
            tracks[f"{t['file']}#{si}"] = [(p[0], p[1]) for p in seg]
    graph = json.load(open(GRAPH))
    trails = {t['id']: t['name'] for t in graph['trails']}
    rows = []
    for s in graph['segments']:
        geo = json.load(open(os.path.join(GEOM, f"{s['id']}.json")))
        arc = geo['derived']['arc']
        raw = tracks[arc['track']]
        a, b = sorted((arc['from'], arc['to']))
        pts = raw[a:b + 1]
        cum = [0.0]
        for p, q in zip(pts, pts[1:]):
            cum.append(cum[-1] + hav(p, q))
        already = arc.get('skip') or []
        for c in candidates(pts, cum):
            i0, i1 = a + c['i'], a + c['j']
            if any(lo <= i0 and i1 <= hi for lo, hi in already):
                continue
            mile = round(cum[c['i']] * M2MI, 2) if not arc['reversed'] else round((cum[-1] - cum[c['i']]) * M2MI, 2)
            rows.append(dict(seg=s['id'], name=s['name'], trail=trails[s['trails'][0]], track=arc['track'],
                             i0=i0, i1=i1, mile=mile, loop=[(p[0], p[1]) for p in pts[c['i']:c['j'] + 1]],
                             context=[(p[0], p[1]) for p in pts[max(0, c['i'] - 40):min(len(pts), c['j'] + 41)]],
                             **{k: c[k] for k in ('loop_m', 'gap_m', 'retrace')}))
    rows.sort(key=lambda r: (-r['retrace'], -r['loop_m']))
    for r in rows:
        print(f"{r['seg']} @{r['mile']:5.2f}mi loop {r['loop_m']:4}m gap {r['gap_m']:4}m retrace {r['retrace']:.2f}  "
              f"skip [{r['i0']}, {r['i1']}]  {r['name'][:50]}")
    print(f"{len(rows)} candidates")
    if sheet:
        write_sheet(rows, sheet)
        print(f"wrote {sheet}")


def write_sheet(rows, path):
    cards = []
    for n, r in enumerate(rows, 1):
        la = sum(p[0] for p in r['loop']) / len(r['loop']); lo = sum(p[1] for p in r['loop']) / len(r['loop'])
        cards.append(f'''<section class="card" id="c{n}">
  <h2>{n}. <code>{r['seg']}</code> {r['name']} <small>@ {r['mile']} mi</small></h2>
  <p class="meta">loop {r['loop_m']} m · gap {r['gap_m']} m · retrace {r['retrace']:.2f} · <code>"skip": [[{r['i0']}, {r['i1']}]]</code> in geometry/{r['seg']}.json · track {r['track']}</p>
  <div class="map" data-c="{la:.6f},{lo:.6f}" data-loop='{json.dumps(r['loop'])}' data-ctx='{json.dumps(r['context'])}'></div>
  <label><input type="checkbox" data-seg="{r['seg']}" data-skip="[{r['i0']}, {r['i1']}]"> detour — excise</label>
</section>''')
    html = f'''<!doctype html><html><head><meta charset="utf-8"><title>Detour candidates</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>body{{font:15px/1.5 system-ui;margin:0;padding:1rem 2rem;background:#17150f;color:#faf6ef}}h1{{font-weight:600}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(520px,1fr));gap:1.4rem}}.card{{background:#221f16;border-radius:8px;padding:.8rem 1rem}}
.card h2{{font-size:1.05rem;margin:0 0 .2rem}}.meta{{margin:0 0 .5rem;font-size:.8rem;color:#b9b2a3}}.map{{height:340px;border-radius:6px}}
label{{display:block;margin-top:.5rem}}code{{color:#d9a441}}#out{{position:sticky;top:0;background:#17150f;padding:.6rem 0;border-bottom:1px solid #444}}
textarea{{width:100%;height:5rem;background:#221f16;color:#faf6ef;border:1px solid #444;font-family:ui-monospace,monospace}}</style></head><body>
<h1>Detour candidates — {len(rows)}</h1>
<p>Red is the candidate loop, yellow the surrounding track. Likeliest detours first (a spur retraces itself; a switchback diverges). Tick the real ones; the box below collects the <code>skip</code> entries to paste.</p>
<div id="out"><textarea id="picks" readonly placeholder="ticked candidates appear here"></textarea></div>
<div class="grid">{''.join(cards)}</div>
<script>
document.querySelectorAll('.map').forEach(el=>{{const [la,lo]=el.dataset.c.split(',').map(Number);
const m=L.map(el,{{zoomControl:false,attributionControl:false,scrollWheelZoom:false}}).setView([la,lo],18);
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',{{maxNativeZoom:18,maxZoom:20}}).addTo(m);
L.polyline(JSON.parse(el.dataset.ctx),{{color:'#ffd400',weight:2,opacity:.8}}).addTo(m);
L.polyline(JSON.parse(el.dataset.loop),{{color:'#ff3b30',weight:3}}).addTo(m);L.control.scale({{imperial:false}}).addTo(m);}});
const out=document.getElementById('picks');
document.querySelectorAll('input[type=checkbox]').forEach(cb=>cb.addEventListener('change',()=>{{
const by={{}};document.querySelectorAll('input:checked').forEach(c=>{{(by[c.dataset.seg]=by[c.dataset.seg]||[]).push(c.dataset.skip)}});
out.value=Object.entries(by).map(([s,k])=>`${{s}}: "skip": [${{k.join(', ')}}]`).join('\\n');}}));
</script></body></html>'''
    open(path, 'w').write(html)


if __name__ == '__main__':
    main()
