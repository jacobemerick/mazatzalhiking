#!/usr/bin/env node
/* Fail if any link inside the built site goes nowhere (#53, item 1).
 *
 * The markdown render hook already refuses a bad link written in content/. This covers
 * everything else that ends up in public/: links in templates, asset paths, the
 * canonical/og/JSON-LD URLs, sitemap.xml and robots.txt, url() in CSS, and the
 * literal paths the builder's JS fetches. Offline; nothing is requested.
 *
 * A path resolves the way the Workers asset server resolves it: /x/ is x/index.html,
 * /x is the file x, x.html or x/index.html. Paths wrangler.jsonc sends to the Worker
 * script (run_worker_first) are served by code, not files, and count as present.
 * A #fragment must name an id on the target page.
 *
 *   node tools/check_links.mjs        # after hugo has built public/
 */
import { readFileSync, readdirSync, existsSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, relative, extname } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const PUBLIC = join(ROOT, 'public');
const ORIGIN = new URL(readFileSync(join(ROOT, 'hugo.toml'), 'utf8').match(/^baseURL\s*=\s*"([^"]+)"/m)[1]).origin;

// Worker-served paths, from wrangler.jsonc (comments stripped; the file is otherwise JSON).
const wrangler = JSON.parse(readFileSync(join(ROOT, 'wrangler.jsonc'), 'utf8').replace(/^\s*\/\/.*$/gm, ''));
const workerRoutes = (wrangler.assets?.run_worker_first || []).map(p =>
  new RegExp('^' + p.replace(/[.+?^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*') + '$'));

function walk(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap(e =>
    e.isDirectory() ? walk(join(dir, e.name)) : [join(dir, e.name)]);
}

const isFile = p => existsSync(p) && statSync(p).isFile();

// URL path -> the file the asset server would answer with, or null.
function resolve(path) {
  let p;
  try { p = decodeURIComponent(path); } catch { return null; }
  const f = join(PUBLIC, p);
  if (!f.startsWith(PUBLIC)) return null;
  if (p.endsWith('/')) return isFile(join(f, 'index.html')) ? join(f, 'index.html') : null;
  for (const c of [f, f + '.html', join(f, 'index.html')]) if (isFile(c)) return c;
  return null;
}

const idCache = new Map();
function ids(file) {
  if (!idCache.has(file)) {
    const html = readFileSync(file, 'utf8');
    idCache.set(file, new Set([...html.matchAll(/\s(?:id|name)=["']?([^"'\s>]+)/g)].map(m => m[1])));
  }
  return idCache.get(file);
}

// Every link-shaped string in a built file, as [raw value, base URL to resolve against].
function links(file, text) {
  const page = '/' + relative(PUBLIC, file).split('\\').join('/');
  const found = [];
  const add = v => { v = v.trim(); if (v) found.push(v); };
  const ext = extname(file);
  if (ext === '.html') {
    for (const m of text.matchAll(/\s(?:href|src|action|poster)=(?:"([^"]*)"|'([^']*)')/g)) add(m[1] ?? m[2]);
    for (const m of text.matchAll(/\ssrcset=(?:"([^"]*)"|'([^']*)')/g))
      for (const part of (m[1] ?? m[2]).split(',')) add(part.trim().split(/\s+/)[0]);
  }
  if (ext === '.css') for (const m of text.matchAll(/url\(\s*['"]?([^'")]+)['"]?\s*\)/g)) add(m[1]);
  // A literal root path to a file (e.g. '/data/graph.json'); a prefix built up with + is skipped.
  if (ext === '.js') for (const m of text.matchAll(/['"`](\/[\w./-]*\.[a-z0-9]+)['"`]/gi)) add(m[1]);
  // Absolute URLs on this site, anywhere: canonical, og:*, JSON-LD, sitemap, robots.txt.
  const esc = ORIGIN.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  for (const m of text.matchAll(new RegExp(esc + '[^\\s"\'<>)\\\\]*', 'g'))) add(m[0]);
  return found.map(v => [v, ORIGIN + page]);
}

const problems = [];
let checked = 0;
for (const file of walk(PUBLIC)) {
  if (!['.html', '.css', '.js', '.xml', '.txt'].includes(extname(file))) continue;
  if (file.startsWith(join(PUBLIC, 'data'))) continue;
  const text = readFileSync(file, 'utf8');
  for (const [raw, base] of links(file, text)) {
    if (/^(mailto|tel|javascript|data|blob):/i.test(raw)) continue;
    let u;
    try { u = new URL(raw.replace(/&amp;/g, '&'), base); } catch { problems.push([file, raw, 'is not a URL']); continue; }
    if (u.origin !== ORIGIN) continue;
    checked++;
    if (workerRoutes.some(r => r.test(u.pathname))) continue;
    const target = resolve(u.pathname);
    if (!target) { problems.push([file, raw, `${u.pathname} is not a file in public/`]); continue; }
    const frag = decodeURIComponent(u.hash.slice(1));
    if (frag && target.endsWith('.html') && !ids(target).has(frag))
      problems.push([file, raw, `#${frag} is not an id on ${u.pathname}`]);
  }
}

for (const [file, raw, why] of problems) console.error(`BROKEN ${relative(ROOT, file)}: "${raw}" -- ${why}`);
if (!checked) { console.error('check_links: found no links in public/ -- did hugo run?'); process.exit(1); }
console.log(`check_links: ${checked} links checked, ${problems.length ? `${problems.length} broken` : 'all resolve'}`);
process.exit(problems.length ? 1 : 0);
