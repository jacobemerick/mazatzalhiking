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
 *   - click a leg that does not connect: the route is unchanged and the popup offers
 *     to start again there; undo removes the last leg
 *   - encode() -> decode() gives the same route back, and so does reloading its URL
 *   - Download GPX and Download KML: each parses as XML, holds the route's full
 *     geometry, names every place passed, and carries the legs' condition notes
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
const C = G.segments.find(c => !touches(c, tailNode) && c.id !== A.id && c.id !== B.id);
const legGain = (s, rev) => rev ? s.loss_ft : s.gain_ft;
const want = {
  route: [{ id: A.id, rev: true }, { id: B.id, rev: bRev }],
  r: `-${A.id}.${bRev ? '-' : ''}${B.id}`,
  miles: (A.miles + B.miles).toFixed(1),
  gain: Math.round(legGain(A, true) + legGain(B, bRev)).toLocaleString('en-US'),
  loss: Math.round(legGain(A, false) + legGain(B, !bRev)).toLocaleString('en-US'),
  places: [A.to, A.from, tailNode].map(n => NODE[n].name),
  trails: [...A.trails, ...B.trails].map(t => G.trails.find(x => x.id === t).name),
  notes: [...notes(A.id), ...notes(B.id)].map(o => o.text),
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
  })`);

  await click(A.id);
  await click(B.id);
  let p = await panel();
  check(same(p.route, want.route), `route after clicking ${A.id} then ${B.id} is ${JSON.stringify(p.route)}, expected ${JSON.stringify(want.route)}`);
  check(p.r === want.r, `URL has ?r=${p.r}, expected ${want.r}`);
  check(p.legs === '2' && p.items === 2, `panel shows ${p.legs} legs and ${p.items} list items, expected 2`);
  check(p.miles === want.miles, `panel shows ${p.miles} mi, expected ${want.miles}`);
  check(p.gain === want.gain, `panel shows ${p.gain} ft gain, expected ${want.gain}`);
  check(p.loss === want.loss, `panel shows ${p.loss} ft loss, expected ${want.loss}`);

  await click(C.id);
  p = await panel();
  check(same(p.route, want.route), `clicking ${C.id}, which does not connect, changed the route to ${JSON.stringify(p.route)}`);
  check(p.popup.includes('Start a new route here'), `clicking ${C.id}, which does not connect, did not offer to start a new route there`);

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
    const all = sel => [...doc.getElementsByTagName(sel)];
    return { file: window.__file, error: err && err.textContent,
      trkseg: all('trkseg').length, trkpt: all('trkpt').length,
      ends: all('trkseg').map(t => { const p = t.getElementsByTagName('trkpt'); return [p[0], p[p.length - 1]].map(q => q.getAttribute('lon') + ',' + q.getAttribute('lat')); }),
      line: all('LineString').map(l => l.getElementsByTagName('coordinates')[0].textContent.trim().split(/\\s+/).map(c => c.split(',').slice(0, 2).join(','))),
      // A KML description is HTML (in CDATA), so read it the way Google Earth does.
      names: [...all('name'), ...all('desc')].map(e => e.textContent)
        .concat(all('description').map(e => new DOMParser().parseFromString(e.textContent, 'text/html').body.textContent))
        .join('\\n') };
  })`);

  const geom = await Promise.all([A, B].map(s => fetch(`${site.origin}/data/${s.geometry}`).then(r => r.json())));
  const points = geom.reduce((n, g) => n + g.coordinates.length, 0);
  // Each leg's first and last point in walking order, as the exports write them.
  const fix = c => c[0].toFixed(6) + ',' + c[1].toFixed(6);
  const walked = [[geom[0], true], [geom[1], bRev]].map(([g, rev]) => {
    const c = rev ? g.coordinates.slice().reverse() : g.coordinates; return [fix(c[0]), fix(c[c.length - 1])]; });
  for (const kind of ['gpx', 'kml']) {
    const f = await download(kind);
    check(!f.error, `${kind.toUpperCase()} does not parse: ${f.error}`);
    check(f.file?.endsWith(`.${kind}`), `${kind.toUpperCase()} downloads as "${f.file}"`);
    if (kind === 'gpx') {
      check(f.trkseg === 2 && f.trkpt === points, `GPX has ${f.trkseg} track segments and ${f.trkpt} points, expected 2 and ${points}`);
      check(same(f.ends, walked), `GPX legs run ${JSON.stringify(f.ends)}, expected ${JSON.stringify(walked)} (walking order)`);
    } else {
      const line = f.line[0] || [];
      check(f.line.length === 1 && line.length === points - 1, `KML line has ${line.length} points, expected ${points - 1} (legs joined at the shared node)`);
      check(line[0] === walked[0][0] && line[line.length - 1] === walked[1][1], `KML line runs ${line[0]} to ${line[line.length - 1]}, expected ${walked[0][0]} to ${walked[1][1]}`);
    }
    for (const name of [...want.places, ...want.trails]) check(f.names.includes(name), `${kind.toUpperCase()} does not mention "${name}"`);
    for (const text of want.notes) check(f.names.includes(text), `${kind.toUpperCase()} is missing the note "${text.slice(0, 60)}"`);
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
