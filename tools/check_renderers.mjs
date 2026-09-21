#!/usr/bin/env node
/* Fail the build if the Hugo observation partial and public/js/conditions.js disagree.
 *
 * #19 requires one rendering of condition observations on every surface. There are
 * now two implementations -- layouts/partials/observations.html for the pages and
 * conditions.js for the builder -- so the rule is enforced here rather than by
 * construction: render every target's observations through the real conditions.js
 * (under a DOM just big enough for it) and compare with what Hugo wrote into the
 * built pages. Any difference in structure, wording, ordering or date format fails.
 *
 *   node tools/check_renderers.mjs        # after hugo has built public/
 */
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

class Element {
  constructor(tag) { this.tag = tag; this.attrs = {}; this.children = []; this._text = null; }
  set className(v) { this.attrs['class'] = v; }
  get className() { return this.attrs['class'] || ''; }
  set textContent(v) { this._text = String(v); this.children = []; }
  get textContent() { return this._text ?? this.children.map(c => c.textContent).join(''); }
  appendChild(c) { this.children.push(c); return c; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  toString() {
    const a = Object.entries(this.attrs).map(([k, v]) => ` ${k}="${esc(v)}"`).join('');
    const inner = this._text != null ? esc(this._text) : this.children.map(String).join('');
    return `<${this.tag}${a}>${inner}</${this.tag}>`;
  }
}
globalThis.window = globalThis;
globalThis.document = { createElement: tag => new Element(tag) };
new Function(readFileSync(join(ROOT, 'public/js/conditions.js'), 'utf8'))();

// Both sides escape differently at the margins (Go emits &#39;, the shim does not
// touch apostrophes) and Hugo may reflow whitespace between tags. Compare the
// meaning, not the bytes.
const norm = h => h
  .replace(/>\s+</g, '><').replace(/\s+/g, ' ').trim()
  .replace(/&#39;/g, "'").replace(/&#43;/g, '+').replace(/&#34;|&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
  .replace(/=([a-zA-Z0-9-]+)(?=[ >])/g, '="$1"');        // unquoted attributes from --minify

const obs = JSON.parse(readFileSync(join(ROOT, 'static/data/observations.json'), 'utf8'));
const by = window.Conditions.index(obs);
const trailsDir = join(ROOT, 'public/trails');
let checked = 0, failed = 0;
for (const slug of readdirSync(trailsDir)) {
  const page = join(trailsDir, slug, 'index.html');
  if (!existsSync(page)) continue;
  const html = readFileSync(page, 'utf8');
  // every leg: <li class="leg" id="XX"> ... <div class="obs-list">...</div>
  const re = /<(?:li class="?leg"? id="?([0-9A-Za-z]+)"?|div class="?place"? id="?node-([0-9A-Za-z]+)"?)>[\s\S]*?(<div class="?obs-list"?>[\s\S]*?<\/div>)\s*<\/(?:li|div)>/g;
  let m;
  while ((m = re.exec(html))) {
    const target = m[1] ? `segment:${m[1]}` : `node:${m[2]}`;
    const want = norm(String(window.Conditions.render(by[target])));
    const got = norm(m[3]);
    checked++;
    if (want !== got) {
      failed++;
      console.error(`MISMATCH ${slug} ${target}\n  hugo: ${got.slice(0, 300)}\n  js:   ${want.slice(0, 300)}`);
    }
  }
}
if (!checked) { console.error('check_renderers: found no observation blocks in public/trails -- did hugo run?'); process.exit(1); }
console.log(`check_renderers: ${checked} observation blocks agree with conditions.js${failed ? `, ${failed} do not` : ''}`);
process.exit(failed ? 1 : 0);
