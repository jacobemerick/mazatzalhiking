#!/usr/bin/env python3
"""Generate the trail list and the per-trail pages (#30, #31, #32, #34).

    ./tools/build_pages.py           # validate, then write public/trails/
    ./tools/build_pages.py --check   # validate and compare, write nothing

Reads the authored graph and observations under `curation/` and writes static HTML
under `public/trails/`: one index page and one page per trail. Nothing here is
authored; every file under `public/trails/` is regenerated wholesale on every run,
stale ones are removed, and the run is idempotent. Decisions in docs/site-pages.md.

## What a trail page is

A segment page with a trail heading (#20). The trail's legs in walking order, and
under each leg its dated condition observations, newest first, or the honest empty
state. Distances and elevation come from the leg's own recorded line. Photos appear
only as context attached to an observation. There is no prose about the trail unless
Jacob wrote it, and today none has been.

## Leg order

A trail's legs are chained by their shared nodes. The chain starts at a trailhead when
exactly one end is one, otherwise at the lower end -- trails are conventionally read
from the bottom up. A leg walked against its recorded direction has its gain and loss
swapped, so the figures on the page are for the direction the page describes. A leg
that starts and ends at the same node (the Saddle Mountain Mine Loop) is listed right
after the leg that arrives at that node.

## The observation renderer is not reimplemented here

#19 requires one renderer for observations on every surface. This tool runs the site's
own `public/js/conditions.js` under Node with a minimal DOM
(`tools/render_conditions.mjs`) and pastes the result in, so the pages and the builder
cannot show conditions differently by construction.
"""
import html, json, os, re, subprocess, sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import validate_graph as V

CURATION = os.path.join(ROOT, 'curation')
PUBLIC = os.path.join(ROOT, 'public')
OUT = os.path.join(PUBLIC, 'trails')
SITEMAP = os.path.join(PUBLIC, 'sitemap.xml')
SITE = 'https://mazatzalhiking.com'
CHECK = '--check' in sys.argv

FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
           "%3Crect width='32' height='32' fill='%2317150f'/%3E%3Cpath d='M4 24l7-11 4 6 3-5 10 10z' "
           "fill='%23d9a441'/%3E%3C/svg%3E")
ANALYTICS = ('<script type=\'module\' src=\'https://static.cloudflareinsights.com/beacon.min.js\' '
             'data-cf-beacon=\'{"token": "5b79bb3f6d16425f920c429acb8d4a59"}\'></script>')


def e(s):
    return html.escape(str(s), quote=True)


def fmt_int(n):
    return f'{int(round(n)):,}'


def fmt_date(iso):
    """Same shape conditions.js uses for observation dates: 'Nov 17, 2017'."""
    d = date.fromisoformat(iso)
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def order_legs(trail_id, segments, nodes):
    """Chain a trail's legs into walking order. Returns [(segment, reversed), ...]."""
    legs = [s for s in segments if trail_id in s['trails']]
    loops = [s for s in legs if s['from'] == s['to']]
    path = [s for s in legs if s['from'] != s['to']]
    if not path:
        return [(s, False) for s in legs]

    adj = {}
    for s in path:
        adj.setdefault(s['from'], []).append(s)
        adj.setdefault(s['to'], []).append(s)
    ends = [n for n, ss in adj.items() if len(ss) == 1]
    if len(ends) != 2 or any(len(ss) > 2 for ss in adj.values()):
        V.warn(f"trail {trail_id!r}: legs do not form a single path; listing them in file order")
        return [(s, False) for s in legs]

    # Start at the trailhead if exactly one end is one, else at the lower end.
    def rank(nid):
        n = nodes[nid]
        return (0 if n['kind'] == 'trailhead' else 1, n.get('ele_ft') or 0, nid)
    start = min(ends, key=rank)

    out, at, used = [], start, set()
    while True:
        nxt = [s for s in adj.get(at, []) if s['id'] not in used]
        if not nxt:
            break
        s = nxt[0]
        used.add(s['id'])
        rev = s['to'] == at
        out.append((s, rev))
        at = s['from'] if rev else s['to']
        for lp in loops:
            if lp['from'] == at and lp['id'] not in used:
                used.add(lp['id'])
                out.append((lp, False))
    return out


def leg_figures(seg, rev):
    gain, loss = (seg['loss_ft'], seg['gain_ft']) if rev else (seg['gain_ft'], seg['loss_ft'])
    a, b = (seg['to'], seg['from']) if rev else (seg['from'], seg['to'])
    return a, b, gain, loss


def render_observations(obs, targets):
    p = subprocess.run(['node', os.path.join(HERE, 'render_conditions.mjs')],
                       input=json.dumps({'observations': obs, 'targets': targets}),
                       capture_output=True, text=True)
    if p.returncode:
        sys.exit(f"render_conditions.mjs failed:\n{p.stderr}")
    return json.loads(p.stdout)


def page(title, description, canonical, body, *, noindex=False):
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)} — Mazatzal Hiking</title>
<meta name="description" content="{e(description)}">
<link rel="canonical" href="{e(SITE + canonical)}">
{'<meta name="robots" content="noindex">' if noindex else ''}
<meta name="theme-color" content="#17150f">
<meta property="og:title" content="{e(title)} — Mazatzal Hiking">
<meta property="og:description" content="{e(description)}">
<meta property="og:type" content="website">
<link rel="icon" href="{FAVICON}">
<link rel="stylesheet" href="/css/site.css">
</head>
<body>
<header class="site-head">
  <div class="wrap">
    <a class="brand" href="/">
      <svg width="20" height="20" viewBox="0 0 32 32" aria-hidden="true"><path d="M2 26l8-13 4.5 7L18 14l12 12z" fill="#d9a441"/></svg>
      Mazatzal Hiking
    </a>
    <nav class="site-nav"><a href="/trails/">Trails</a><a href="/about/">About</a></nav>
  </div>
</header>
<main class="wrap">
{body}
</main>
<footer class="site-foot">
  <div class="wrap foot-grid">
    <span>Built by <a href="https://jacobemerick.com">Jacob Emerick</a></span>
    <div class="foot-links">
      <a href="/trails/">Trails</a>
      <a href="/about/">About</a>
      <a href="https://github.com/jacobemerick/mazatzalhiking">GitHub</a>
      <a href="https://www.fs.usda.gov/tonto">Tonto National Forest</a>
    </div>
  </div>
</footer>
{ANALYTICS}
</body>
</html>
'''


def trail_page(trail, legs, nodes, obs_html):
    miles = sum(s['miles'] for s, _ in legs)
    gain = sum(leg_figures(s, r)[2] for s, r in legs)
    loss = sum(leg_figures(s, r)[3] for s, r in legs)
    first = nodes[leg_figures(*legs[0])[0]]
    last = nodes[leg_figures(*legs[-1])[1]]
    route = '.'.join(('-' if r else '') + s['id'] for s, r in legs)
    kind = 'Forest road' if trail['kind'] == 'road' else 'Trail'
    code = f"{kind} {e(trail['code'])}" if trail.get('code') else kind
    dates = sorted({src['date'] for s, _ in legs for src in s['sources']})
    recorded = (f"recorded on {fmt_date(dates[0])}" if len(dates) == 1
                else f"recorded on {len(dates)} trips between {fmt_date(dates[0])} and {fmt_date(dates[-1])}")

    legs_html = []
    for i, (s, rev) in enumerate(legs, 1):
        a, b, g, l = leg_figures(s, rev)
        loop = s['from'] == s['to']
        legs_html.append(f'''
  <li class="leg" id="{e(s['id'])}">
    <h2>{e(s['name'])}</h2>
    <p class="leg-meta">
      <span>{e(nodes[a]['name'])} &rarr; {e(nodes[b]['name'])}{' (loop)' if loop else ''}</span>
      <span>{s['miles']:.2f} mi</span>
      <span>+{fmt_int(g)} ft / &minus;{fmt_int(l)} ft</span>
    </p>
    {obs_html['segment:' + s['id']]}
  </li>''')

    body = f'''
<article class="trail">
  <p class="eyebrow">{code} &middot; Tonto National Forest</p>
  <h1>{e(trail['name'])}</h1>
  <p class="trail-route">{e(first['name'])} to {e(last['name'])}</p>
  <dl class="stats">
    <div><dt>Distance</dt><dd>{miles:.1f} mi</dd></div>
    <div><dt>Gain</dt><dd>{fmt_int(gain)} ft</dd></div>
    <div><dt>Loss</dt><dd>{fmt_int(loss)} ft</dd></div>
    <div><dt>Legs</dt><dd>{len(legs)}</dd></div>
  </dl>
  <p class="actions"><a class="btn" href="/build/?r={e(route)}">Open in the route builder</a></p>
  <p class="provenance">Every leg below is a GPS track that was walked and {recorded}. Distance is measured along the recorded line; elevation comes from USGS 3DEP lidar sampled along it. Condition notes carry the date they were observed. A leg with no note is a leg with nothing recorded — not a clear trail.</p>
  <ol class="legs">{''.join(legs_html)}
  </ol>
</article>'''
    desc = (f"{trail['name']} in the Mazatzal Wilderness: {miles:.1f} miles from {first['name']} to "
            f"{last['name']} in {len(legs)} leg{'s' if len(legs) != 1 else ''}, from GPS tracks that "
            f"were walked and recorded, with dated condition notes.")
    return page(trail['name'], desc, f"/trails/{trail['slug']}/", body)


def index_page(rows):
    def group(kind, heading, note):
        items = [r for r in rows if r['kind'] == kind]
        if not items:
            return ''
        lis = ''.join(f'''
    <li><a href="/trails/{e(r['slug'])}/">{e(r['name'])}</a>
      <span class="meta">{r['miles']:.1f} mi &middot; {r['legs']} leg{'s' if r['legs'] != 1 else ''}</span></li>'''
                      for r in items)
        return f'''
<section>
  <h2>{heading}</h2>
  <p class="note">{note}</p>
  <ul class="trail-list">{lis}
  </ul>
</section>'''
    total = sum(r['miles'] for r in rows)
    body = f'''
<p class="eyebrow">Mazatzal Wilderness &middot; Tonto National Forest</p>
<h1>Trails</h1>
<p class="lede">{len(rows)} trails and roads, {total:.0f} miles, every one of them a GPS track that was walked and recorded. Each page lists the trail leg by leg with dated condition notes where they exist.</p>
{group('trail', 'Trails', 'Listed alphabetically.')}
{group('road', 'Forest roads', 'Roads that were walked as part of a route. They are in the network because a hike used them, not because they exist.')}'''
    desc = (f"Every trail in the Mazatzal Wilderness that has been walked and recorded: {len(rows)} trails "
            f"and roads, {total:.0f} miles, listed leg by leg with dated condition notes.")
    return page('Trails', desc, '/trails/', body)


def main():
    graph = json.load(open(os.path.join(CURATION, 'graph.json')))
    obs_path = os.path.join(CURATION, 'observations.json')
    obs = json.load(open(obs_path))
    V.check(graph, obs, obs_path)
    nodes = {n['id']: n for n in graph['nodes']}

    ordered = {t['id']: order_legs(t['id'], graph['segments'], nodes) for t in graph['trails']}
    for w in V.warnings:
        print(f"  warn  {w}")
    for x in V.errors:
        print(f"  ERROR {x}")
    if V.errors:
        sys.exit(f"\n{len(V.errors)} error(s); nothing written.")

    obs_html = render_observations(obs, [f"segment:{s['id']}" for s in graph['segments']])

    files = {}
    rows = []
    for t in graph['trails']:
        legs = ordered[t['id']]
        if not legs:
            V.warn(f"trail {t['id']!r} ({t['name']!r}) has no legs; no page")
            continue
        files[os.path.join(t['slug'], 'index.html')] = trail_page(t, legs, nodes, obs_html)
        rows.append(dict(name=t['name'], slug=t['slug'], kind=t['kind'],
                         miles=sum(s['miles'] for s, _ in legs), legs=len(legs)))
    rows.sort(key=lambda r: r['name'].lower())
    files['index.html'] = index_page(rows)

    # The generator is the one thing that knows every URL, so it writes the sitemap.
    # The builder is deliberately left out until Jacob opens it (it carries noindex).
    urls = ['/', '/trails/', '/about/'] + [f"/trails/{r['slug']}/" for r in rows]
    sitemap = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
               + ''.join(f'  <url><loc>{e(SITE + u)}</loc></url>\n' for u in urls)
               + '</urlset>\n')

    changed = []
    for dst, body in [(os.path.join(OUT, rel), body) for rel, body in files.items()] + [(SITEMAP, sitemap)]:
        old = open(dst).read() if os.path.exists(dst) else None
        if old != body:
            changed.append(os.path.relpath(dst, PUBLIC))
            if not CHECK:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                open(dst, 'w').write(body)
    stale = []
    for dp, dns, fns in os.walk(OUT, topdown=False):
        for fn in fns:
            rel = os.path.relpath(os.path.join(dp, fn), OUT)
            if rel not in files:
                stale.append(rel)
                if not CHECK:
                    os.remove(os.path.join(dp, fn))
        if not CHECK and dp != OUT and not os.listdir(dp):
            os.rmdir(dp)

    verb = 'would write' if CHECK else 'wrote'
    n_obs = sum(1 for h in obs_html.values() if 'obs-empty' not in h)
    print(f"{len(rows)} trail pages, {sum(r['miles'] for r in rows):.1f} mi; "
          f"{n_obs} of {len(obs_html)} legs have observations")
    print(f"{verb} {len(changed)} file(s), removed {len(stale)} stale" if changed or stale
          else "public/trails and sitemap.xml are up to date")
    if CHECK and (changed or stale):
        sys.exit(1)


if __name__ == '__main__':
    main()
