#!/usr/bin/env node
/* Fail the build if the route builder's four launch surfaces disagree with the
 * launch switch, builderPublic in hugo.toml (#47).
 *
 *   off: /build/ carries noindex, robots.txt disallows /build/, the sitemap leaves it
 *        out, and the landing page does not link to it
 *   on:  none of those; /build/ is in the sitemap and the landing page links to it
 *
 *   node tools/check_launch.mjs        # after hugo has built public/
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const read = p => readFileSync(join(ROOT, p), 'utf8');
const flag = read('hugo.toml').match(/^\s*builderPublic\s*=\s*(true|false)\s*$/m);
if (!flag) { console.error('check_launch: builderPublic = true|false not found in hugo.toml'); process.exit(1); }
const on = flag[1] === 'true';

const surfaces = {
  'the builder page carries noindex': /<meta name="robots" content="noindex">/.test(read('public/build/index.html')),
  'robots.txt disallows /build/': /^Disallow: \/build\/$/m.test(read('public/robots.txt')),
  'the sitemap leaves out /build/': !/<loc>[^<]*\/build\/<\/loc>/.test(read('public/sitemap.xml')),
  'the landing page does not link to /build/': !/href="\/build\/"/.test(read('public/index.html')),
};
const wrong = Object.entries(surfaces).filter(([, hidden]) => hidden === on).map(([what]) => what);
for (const what of wrong) console.error(`LAUNCH builderPublic is ${on}, but ${on ? what : what.replace(/ does not| leaves out| carries| disallows/, m => ({ ' does not': ' does', ' leaves out': ' lists', ' carries': ' lacks', ' disallows': ' allows' })[m])}`);
console.log(`check_launch: builder is ${on ? 'public' : 'hidden'}; ${wrong.length ? `${wrong.length} of 4 surfaces disagree` : 'all 4 surfaces agree'}`);
process.exit(wrong.length ? 1 : 0);
