#!/usr/bin/env node
/* Validate the data against its published JSON Schemas (#53, item 5).
 *
 * validate_graph.py checks the invariants that matter to the site; the schemas under
 * schema/ are the published contract for the same files. This holds the data to them:
 *
 *   curation/graph.json             schema/graph.schema.json
 *   curation/geometry/<id>.json     schema/geometry.schema.json
 *   the notes in content/trails/    schema/observations.schema.json
 *     (parsed by tools/build_site.py --observations; the build never writes them out)
 *   schema/example/*.json           their schemas, so the examples stay true
 *
 * Draft 2020-12, formats (dates) checked. Needs no build.
 *
 *   node tools/check_schema.mjs
 */
import { readFileSync, readdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const json = p => JSON.parse(readFileSync(join(ROOT, p), 'utf8'));

const ajv = new Ajv2020({ allErrors: true, strict: true });
addFormats(ajv);
const schema = name => ajv.compile(json(`schema/${name}.schema.json`));
const graph = schema('graph'), geometry = schema('geometry'), observations = schema('observations');

const notes = JSON.parse(execFileSync('python3', [join(ROOT, 'tools/build_site.py'), '--observations'], { encoding: 'utf8' }));
const docs = [
  ['curation/graph.json', graph, json('curation/graph.json')],
  ...readdirSync(join(ROOT, 'curation/geometry')).filter(f => f.endsWith('.json')).sort()
    .map(f => [`curation/geometry/${f}`, geometry, json(`curation/geometry/${f}`)]),
  ['content/trails/*.md (the notes)', observations, notes],
  ['schema/example/graph.json', graph, json('schema/example/graph.json')],
  ['schema/example/observations.json', observations, json('schema/example/observations.json')],
];

let failed = 0;
for (const [where, validate, doc] of docs) {
  if (validate(doc)) continue;
  failed++;
  for (const e of validate.errors.slice(0, 10))
    console.error(`INVALID ${where}${e.instancePath || ''}: ${e.message}${e.params && Object.keys(e.params).length ? ' ' + JSON.stringify(e.params) : ''}`);
  if (validate.errors.length > 10) console.error(`        ... and ${validate.errors.length - 10} more in ${where}`);
}
console.log(`check_schema: ${docs.length} documents, ${failed ? `${failed} invalid` : 'all valid'} (${notes.observations.length} notes)`);
process.exit(failed ? 1 : 0);
