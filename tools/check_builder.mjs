#!/usr/bin/env node
/* Drive the route builder in headless Chrome and check it does its job (#53, item 3).
 *
 * The builder is the only logic on the site, and people will carry its exports into
 * the wilderness. So, against the built site:
 *
 *   - click a leg, then a leg that meets its start, so the first leg has to be turned
 *     around: the route, the panel, the totals
 *     (miles, gain and loss for the direction walked) and the ?r= URL all agree with
 *     graph.json
 *   - each leg in the list links to its trail page, and no condition note appears in
 *     the list or a popup (the notes live on the trail pages, not here)
 *   - click a leg that does not connect: the route is unchanged and the popup offers
 *     to start again there; undo removes the last leg
 *   - encode() -> decode() gives the same route back, and so does reloading its URL
 *   - Download GPX and Download KML: each parses as XML and holds one named line per
 *     leg, every point in walking order, and nothing else: no waypoints, no notes
 *
 * The two legs are chosen from the data, not named, so the check follows the graph
 * as it changes.
 *
 *   node tools/check_builder.mjs        # after hugo has built public/
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { ROOT, serve, browser } from './lib/headless.mjs';

const G = JSON.parse(readFileSync(join(ROOT, 'public/data/graph.json'), 'utf8'));
const OBS = JSON.parse(readFileSync(join(ROOT, 'public/data/observations.json'), 'utf8')).observations;
const NODE = Object.fromEntries(G.nodes.map(n => [n.id, n]));
const notes = id => OBS.filter(o => o.target === `segment:${id}`);
const touches = (s, node) => s.from === node || s.to === node;

// Click leg A, then a leg B that touches A's start and not its end. The builder must
// flip A to meet B, so the route walks A backwards: the case where gain and loss swap
// and the exported geometry has to be reversed.
const pairs = G.segments.flatMap(a => G.segments.map(b => [a, b]));
const [A, B] = pairs.find(([a, b]) => a.id !== b.id && a.from !== a.to && notes(a.id).length && notes(b.id).length &&
  touches(b, a.from) && !touches(b, a.to));
const bRev = B.from !== A.from;
const tailNode = bRev ? B.from : B.to;
const C = G.segments.find(c => !touches(c, tailNode) && c.id !== A.id && c.id !== B.id && notes(c.id).length);
const trailNames = s => s.trails.map(t => G.trails.find(x => x.id === t).name).join(' / ');
const legName = (s, rev) => `${trailNames(s)}: ${NODE[rev ? s.to : s.from].name} to ${NODE[rev ? s.from : s.to].name}`;
const legGain = (s, rev) => rev ? s.loss_ft : s.gain_ft;
const want = {
  route: [{ id: A.id, rev: true }, { id: B.id, rev: bRev }],
  r: `-${A.id}.${bRev ? '-' : ''}${B.id}`,
  miles: (A.miles + B.miles).toFixed(1),
  gain: Math.round(legGain(A, true) + legGain(B, bRev)).toLocaleString('en-US'),
  loss: Math.round(legGain(A, false) + legGain(B, !bRev)).toLocaleString('en-US'),
  legNames: [legName(A, true), legName(B, bRev)],
  pages: [A, B].map(s => s.trails.map(t => `/trails/${G.trails.find(x => x.id === t).slug}/`)),
  notes: [...notes(A.id), ...notes(B.id), ...notes(C.id)].map(o => o.text),
};

const failures = [];
const check = (ok, what) => { if (!ok) failures.push(what); };
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

const site = await serve();
const chrome = await browser();
try {
  await chrome.goto(`${site.origin}/build/`);
  await chrome.waitFor(`window.Builder && document.querySelector('path[stroke-width="18"]')`, 'the builder to load');

  // Leaflet keeps no ids on its paths; the hit lines are in display.json key order.
  const click = id => chrome.evaluate(`fetch('/data/display.json').then(r => r.json()).then(d => {
    const i = Object.keys(d.segments).indexOf(${JSON.stringify(id)});
    const hits = document.querySelectorAll('path[stroke-width="18"]');
    if (i < 0 || hits.length !== Object.keys(d.segments).length) throw new Error('cannot find the hit line for ${id}');
    hits[i].dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: 400, clientY: 400 }));
  })`);
  const panel = () => chrome.evaluate(`({
    route: Builder.route.map(l => ({ id: l.id, rev: l.rev })),
    r: new URL(location.href).searchParams.get('r'),
    miles: document.getElementById('st-miles').textContent,
    gain: document.getElementById('st-gain').textContent,
    loss: document.getElementById('st-loss').textContent,
    legs: document.getElementById('st-legs').textContent,
    items: document.querySelectorAll('#legs > li').length,
    popup: document.querySelector('.leaflet-popup-content')?.textContent || '',
    list: document.getElementById('legs').textContent,
    pages: [...document.querySelectorAll('#legs > li')].map(li => [...li.querySelectorAll('.leg-trail a')].map(a => a.getAttribute('href'))),
  })`);
  const noNotes = (text, where) => { for (const n of want.notes) check(!text.includes(n), `${where} shows the note "${n.slice(0, 60)}"`); };

  await click(A.id);
  await click(B.id);
  let p = await panel();
  check(same(p.route, want.route), `route after clicking ${A.id} then ${B.id} is ${JSON.stringify(p.route)}, expected ${JSON.stringify(want.route)}`);
  check(p.r === want.r, `URL has ?r=${p.r}, expected ${want.r}`);
  check(p.legs === '2' && p.items === 2, `panel shows ${p.legs} legs and ${p.items} list items, expected 2`);
  check(p.miles === want.miles, `panel shows ${p.miles} mi, expected ${want.miles}`);
  check(p.gain === want.gain, `panel shows ${p.gain} ft gain, expected ${want.gain}`);
  check(p.loss === want.loss, `panel shows ${p.loss} ft loss, expected ${want.loss}`);
  check(same(p.pages, want.pages), `legs link to ${JSON.stringify(p.pages)}, expected ${JSON.stringify(want.pages)}`);
  for (const href of new Set(p.pages.flat())) {
    const res = await fetch(site.origin + href);
    check(res.ok, `the trail page link ${href} answers ${res.status}`);
  }
  noNotes(p.list, 'the leg list');

  await click(C.id);
  p = await panel();
  check(same(p.route, want.route), `clicking ${C.id}, which does not connect, changed the route to ${JSON.stringify(p.route)}`);
  check(p.popup.includes('Start a new route here'), `clicking ${C.id}, which does not connect, did not offer to start a new route there`);
  noNotes(p.popup, `the popup for ${C.id}`);

  await chrome.evaluate(`document.getElementById('undo').click()`);
  p = await panel();
  check(same(p.route, want.route.slice(0, 1)), `undo left ${JSON.stringify(p.route)}, expected only ${A.id}`);
  await click(B.id);

  const round = await chrome.evaluate(`Builder.decode(Builder.encode())`);
  check(!round.problem && same(round.legs, want.route), `decode(encode()) gave ${JSON.stringify(round)}`);

  // The download buttons, with the blob caught instead of saved.
  const download = kind => chrome.evaluate(`new Promise((ok, fail) => {
    const make = URL.createObjectURL, click = HTMLAnchorElement.prototype.click;
    URL.createObjectURL = b => { URL.createObjectURL = make; b.text().then(ok, fail); return 'blob:caught'; };
    HTMLAnchorElement.prototype.click = function () { HTMLAnchorElement.prototype.click = click; window.__file = this.download; };
    document.getElementById('${kind}').click();
    setTimeout(() => fail(new Error('no ${kind} download after 10s')), 10000);
  }).then(text => {
    const doc = new DOMParser().parseFromString(text, 'application/xml');
    const err = doc.querySelector('parsererror');
    const all = (el, tag) => [...el.getElementsByTagName(tag)];
    const name = el => el.getElementsByTagName('name')[0]?.textContent;
    // Each leg's line as [lon,lat] strings, from a GPX <trk> or a KML <Placemark>.
    const legs = all(doc, 'trk').map(t => ({ name: name(t), pts: all(t, 'trkpt').map(q => q.getAttribute('lon') + ',' + q.getAttribute('lat')) }))
      .concat(all(doc, 'Placemark').map(m => ({ name: name(m),
        pts: (m.getElementsByTagName('coordinates')[0]?.textContent.trim().split(/\\s+/) || []).map(c => c.split(',').slice(0, 2).join(',')) })));
    return { file: window.__file, error: err && err.textContent, legs, text: doc.documentElement.textContent,
      extras: all(doc, 'wpt').length + all(doc, 'Point').length + all(doc, 'desc').length + all(doc, 'description').length };
  })`);

  const geom = await Promise.all([A, B].map(s => fetch(`${site.origin}/data/${s.geometry}`).then(r => r.json())));
  // Each leg's points in walking order, as the exports write them.
  const fix = c => c[0].toFixed(6) + ',' + c[1].toFixed(6);
  const walked = [[geom[0], true], [geom[1], bRev]].map(([g, rev]) => (rev ? g.coordinates.slice().reverse() : g.coordinates).map(fix));
  for (const kind of ['gpx', 'kml']) {
    const f = await download(kind), K = kind.toUpperCase();
    check(!f.error, `${K} does not parse: ${f.error}`);
    check(f.file?.endsWith(`.${kind}`), `${K} downloads as "${f.file}"`);
    check(same(f.legs.map(l => l.name), want.legNames), `${K} legs are named ${JSON.stringify(f.legs.map(l => l.name))}, expected ${JSON.stringify(want.legNames)}`);
    walked.forEach((pts, i) => {
      const got = f.legs[i]?.pts || [];
      check(same(got, pts), `${K} leg ${i + 1} has ${got.length} points from ${got[0]} to ${got[got.length - 1]}, expected ${pts.length} from ${pts[0]} to ${pts[pts.length - 1]}`);
    });
    check(f.extras === 0, `${K} has ${f.extras} waypoints or descriptions; it should hold only the legs`);
    noNotes(f.text, K);
  }

  await chrome.goto(`${site.origin}/build/?r=${want.r}`);
  await chrome.waitFor(`window.Builder && Builder.route.length`, 'the shared route to load');
  p = await panel();
  check(same(p.route, want.route) && p.miles === want.miles, `reloading ?r=${want.r} gave ${JSON.stringify(p.route)}, ${p.miles} mi`);

  for (const e of chrome.errors) check(false, `uncaught error in the page: ${e}`);
} finally {
  await chrome.close();
  site.close();
}

for (const f of failures) console.error(`FAIL ${f}`);
console.log(`check_builder: route ${want.r}, ${want.miles} mi: ${failures.length ? `${failures.length} failures` : 'route, totals, URL and exports all agree'}`);
process.exit(failures.length ? 1 : 0);
