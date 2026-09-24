#!/usr/bin/env node
/* Shared route links keep working (#53, item 4).
 *
 * Every line of tools/fixtures/shared-routes.txt is decoded by the builder itself, in
 * headless Chrome, against the current graph:
 *
 *   ok       loads whole with no problem, and re-encodes to the same legs in the same
 *            order (and to the exact string, when the line carries direction flags)
 *   retired  loads up to the first retired segment, then names what it was split into
 *
 * So does the "Open in the route builder" link on every trail page in this build, and
 * one retired link is opened for real to check the page shows its notice.
 *
 *   node tools/check_routes.mjs        # after hugo has built public/
 */
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { ROOT, serve, browser } from './lib/headless.mjs';

const G = JSON.parse(readFileSync(join(ROOT, 'public/data/graph.json'), 'utf8'));
const RETIRED = Object.fromEntries((G.retired || []).map(r => [r.id, r]));

const fixtures = readFileSync(join(ROOT, 'tools/fixtures/shared-routes.txt'), 'utf8').split('\n')
  .map((line, i) => [line.replace(/#.*/, '').trim(), i + 1])
  .filter(([line]) => line)
  .map(([line, n]) => { const [r, expect] = line.split(/\s+/); return { r, expect, where: `shared-routes.txt:${n}` }; });

const trailLinks = readdirSync(join(ROOT, 'public/trails'), { withFileTypes: true }).filter(d => d.isDirectory()).flatMap(d => {
  const m = readFileSync(join(ROOT, 'public/trails', d.name, 'index.html'), 'utf8').match(/href="\/build\/\?r=([^"]*)"/);
  return m ? [{ r: m[1], expect: 'ok', where: `/trails/${d.name}/` }] : [];
});

const failures = [];
const fail = (f, why) => failures.push(`${f.where} ${f.r}: ${why}`);
const encode = legs => legs.map(l => (l.rev ? '-' : '') + l.id).join('.');
const bare = r => r.split('.').map(t => t.replace(/^-/, '')).join('.');

const site = await serve();
const chrome = await browser();
try {
  await chrome.goto(`${site.origin}/build/`);
  await chrome.waitFor(`window.Builder && document.querySelector('path[stroke-width="18"]')`, 'the builder to load');
  const decoded = await chrome.evaluate(`${JSON.stringify([...fixtures, ...trailLinks].map(f => f.r))}.map(r => Builder.decode(r))`);

  [...fixtures, ...trailLinks].forEach((f, i) => {
    const { legs, problem } = decoded[i];
    const toks = f.r.split('.');
    if (f.expect === 'ok') {
      if (problem) return fail(f, problem);
      const again = encode(legs);
      if (bare(again) !== bare(f.r)) fail(f, `loads as ${again}`);
      else if (f.r.includes('-') && again !== f.r) fail(f, `re-encodes as ${again}`);
    } else if (f.expect === 'retired') {
      const at = toks.findIndex(t => RETIRED[t.replace(/^-/, '')]);
      if (at < 0) return fail(f, 'marked retired, but names no retired segment');
      const r = RETIRED[toks[at].replace(/^-/, '')];
      if (legs.length !== at) fail(f, `loaded ${legs.length} legs, expected ${at} (up to ${r.id})`);
      if (!problem || !problem.includes('was split into ' + r.superseded_by.join(' and ')))
        fail(f, `should say ${r.id} was split into ${r.superseded_by.join(' and ')}; said ${JSON.stringify(problem)}`);
    } else fail(f, `expectation "${f.expect}" is neither ok nor retired`);
  });

  const shown = fixtures.find(f => f.expect === 'retired');
  if (shown) {
    await chrome.goto(`${site.origin}/build/?r=${shown.r}`);
    await chrome.waitFor(`window.Builder && Builder.route.length`, 'the retired link to load');
    const notice = await chrome.evaluate(`(n => !n.hidden && n.textContent)(document.getElementById('notice'))`);
    if (!notice || !notice.includes('was split into')) fail(shown, `opening it shows no split notice (got ${JSON.stringify(notice)})`);
  }
  for (const e of chrome.errors) failures.push(`uncaught error in the page: ${e}`);
} finally {
  await chrome.close();
  site.close();
}

for (const f of failures) console.error(`FAIL ${f}`);
console.log(`check_routes: ${fixtures.length} pinned links and ${trailLinks.length} trail-page links, ${failures.length ? `${failures.length} broken` : 'all load'}`);
process.exit(failures.length ? 1 : 0);
