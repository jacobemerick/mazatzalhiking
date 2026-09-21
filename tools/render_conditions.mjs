#!/usr/bin/env node
/* Render condition observations to HTML for the page generator, using the site's
 * own renderer (public/js/conditions.js) rather than a port of it.
 *
 * #19 says every surface renders observations through one component so they cannot
 * drift. The trail pages are generated ahead of time in Python, which would make a
 * second renderer inevitable -- unless the generator runs the first one. So this
 * loads conditions.js under a DOM just big enough for it (createElement, className,
 * textContent, appendChild, setAttribute) and serialises the result. Escaping is done
 * here, once, on the way out; the renderer only ever sets textContent.
 *
 * stdin:  {"observations": <observations.json>, "targets": ["segment:00", ...]}
 * stdout: {"segment:00": "<div class=\"obs-list\">...</div>", ...}
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'public', 'js', 'conditions.js');

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
new Function(readFileSync(SRC, 'utf8'))();      // defines window.Conditions

const input = JSON.parse(readFileSync(0, 'utf8'));
const by = window.Conditions.index(input.observations);
const out = {};
for (const t of input.targets) out[t] = String(window.Conditions.render(by[t]));
process.stdout.write(JSON.stringify(out));
