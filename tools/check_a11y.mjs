#!/usr/bin/env node
/* Accessibility: axe-core over a representative set of built pages (#53, item 2).
 *
 * Each page is loaded in headless Chrome, left to finish its own scripts, and checked
 * with axe-core (WCAG 2.x A and AA rules). Any violation axe rates serious or critical
 * fails the check; moderate and minor ones are printed but do not fail it.
 *
 * The builder is checked twice: with a route loaded (panel, leg list, buttons), and
 * with a leg's popup open, since that is the part of the app that only exists after
 * a click.
 *
 *   node tools/check_a11y.mjs        # after hugo has built public/
 */
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { serve, browser } from './lib/headless.mjs';

const AXE = readFileSync(createRequire(import.meta.url).resolve('axe-core/axe.min.js'), 'utf8');
const FAIL_ON = new Set(['serious', 'critical']);

const PAGES = [
  { path: '/' },
  { path: '/trails/' },
  { path: '/trails/barnhardt-trail/' },            // a trail page with notes
  { path: '/about/' },
  { path: '/no-such-page/', status: 404 },
  { path: '/build/?r=-00.01', ready: `window.Builder && Builder.route.length === 2` },
  { path: '/build/?r=-00.01', name: '/build/ (popup open)', ready: `window.Builder && Builder.route.length === 2`,
    // Open a leg's popup the way a click does: a non-connecting leg shows its details.
    then: `(() => { const hits = document.querySelectorAll('path[stroke-width="18"]');
      hits[hits.length - 1].dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: 600, clientY: 400 })); })()`,
    thenReady: `document.querySelector('.leaflet-popup-content')` },
];

const site = await serve();
const chrome = await browser();
let failed = 0, noted = 0;
try {
  for (const p of PAGES) {
    const name = p.name || p.path;
    await chrome.goto(site.origin + p.path);
    if (p.ready) await chrome.waitFor(p.ready, `${name} to load`);
    if (p.then) { await chrome.evaluate(p.then); await chrome.waitFor(p.thenReady, `${name} to open`); }
    await chrome.evaluate(AXE);
    const found = await chrome.evaluate(`axe.run(document, {
        runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'] },
        resultTypes: ['violations'] })
      .then(r => r.violations.map(v => ({ id: v.id, impact: v.impact, help: v.help,
        nodes: v.nodes.map(n => n.target.join(' ') + (n.failureSummary ? ' -- ' + n.failureSummary.split('\\n').slice(1).join(' ').trim() : '')) })))`);
    for (const v of found) {
      const bad = FAIL_ON.has(v.impact);
      bad ? failed++ : noted++;
      console[bad ? 'error' : 'log'](`${bad ? 'FAIL' : 'note'} ${name} [${v.impact}] ${v.id}: ${v.help}`);
      for (const n of v.nodes.slice(0, 5)) console[bad ? 'error' : 'log'](`       ${n}`);
      if (v.nodes.length > 5) console[bad ? 'error' : 'log'](`       ... and ${v.nodes.length - 5} more`);
    }
  }
  for (const e of chrome.errors) { failed++; console.error(`FAIL uncaught error in a page: ${e}`); }
} finally {
  await chrome.close();
  site.close();
}

console.log(`check_a11y: ${PAGES.length} page states, ${failed ? `${failed} serious or critical violations` : 'no serious or critical violations'}${noted ? `, ${noted} lesser noted` : ''}`);
process.exit(failed ? 1 : 0);
