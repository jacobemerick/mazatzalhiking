#!/usr/bin/env python3
"""Structural validation for a trail graph instance.

    ./tools/validate_graph.py schema/example/graph.json [observations.json]

Checks the invariants that matter for correctness rather than mere shape: that
references resolve, that the network is actually connected, and that retired ids
stay retired. Exits non-zero on any error, so a build can gate on it.

This is the seed of the validation #16 asks for, not its completion — #16 still has
to check total network mileage against the corpus inventory and wire this into the
build. Written against the stdlib so it runs anywhere with no install step.
"""
import json, sys, os
from collections import defaultdict

errors, warnings = [], []


def err(m):
    errors.append(m)


def warn(m):
    warnings.append(m)


def check(graph, obs=None):
    trails = {t['id']: t for t in graph.get('trails', [])}
    nodes = {n['id']: n for n in graph.get('nodes', [])}
    segments = {s['id']: s for s in graph.get('segments', [])}
    features = {f['id']: f for f in graph.get('features', [])}
    retired = {r['id']: r for r in graph.get('retired', [])}

    # duplicate ids within each space
    for label, items in (('trail', graph.get('trails', [])), ('node', graph.get('nodes', [])),
                         ('segment', graph.get('segments', [])), ('feature', graph.get('features', []))):
        seen = set()
        for it in items:
            if it['id'] in seen:
                err(f"duplicate {label} id {it['id']!r}")
            seen.add(it['id'])

    # a retired id must not be back in circulation
    for rid, r in retired.items():
        if rid in segments:
            err(f"retired id {rid!r} is in use again as a segment — shared route URLs "
                f"pointing at the old leg would silently change meaning")
        for sid in r.get('superseded_by', []):
            if sid not in segments and sid not in retired:
                err(f"retired {rid!r} claims superseded_by {sid!r}, which does not exist")

    # segment references and sanity
    endpoints = defaultdict(list)
    pairs = defaultdict(list)
    for sid, s in segments.items():
        for end in ('from', 'to'):
            if s[end] not in nodes:
                err(f"segment {sid!r} {end} references unknown node {s[end]!r}")
        if s['from'] == s['to']:
            err(f"segment {sid!r} starts and ends at the same node {s['from']!r}")
        if s['miles'] <= 0:
            err(f"segment {sid!r} has non-positive length {s['miles']}")
        if not s.get('trails'):
            err(f"segment {sid!r} has no parent trail")
        for tid in s.get('trails', []):
            if tid not in trails:
                err(f"segment {sid!r} references unknown trail {tid!r}")
        if s['from'] in nodes and s['to'] in nodes:
            endpoints[s['from']].append(sid)
            endpoints[s['to']].append(sid)
            pairs[frozenset((s['from'], s['to']))].append(sid)
        if not s.get('sources'):
            warn(f"segment {sid!r} records no source track — provenance is the point of "
                 f"this project and should survive into the graph")

    for pair, sids in pairs.items():
        if len(sids) > 1:
            warn(f"segments {', '.join(sorted(sids))} all connect the same two nodes; "
                 f"legitimate for genuinely parallel trails, otherwise a duplicate")

    # orphan nodes
    for nid, n in nodes.items():
        if not endpoints[nid]:
            err(f"node {nid!r} ({n['name']!r}) has no segments — orphan")

    # connectivity
    if nodes and segments:
        adj = defaultdict(set)
        for sid, s in segments.items():
            if s['from'] in nodes and s['to'] in nodes:
                adj[s['from']].add(s['to'])
                adj[s['to']].add(s['from'])
        seen, components = set(), []
        for start in nodes:
            if start in seen:
                continue
            stack, comp = [start], []
            seen.add(start)
            while stack:
                k = stack.pop()
                comp.append(k)
                for nb in adj[k]:
                    if nb not in seen:
                        seen.add(nb)
                        stack.append(nb)
            components.append(comp)
        if len(components) > 1:
            components.sort(key=len, reverse=True)
            err(f"network splits into {len(components)} disconnected components "
                f"(largest {len(components[0])} nodes); a route cannot cross between them")
            for c in components[1:]:
                err(f"  stranded: {', '.join(sorted(nodes[n]['name'] for n in c))}")

    # features
    for fid, f in features.items():
        if 'on' in f:
            if f['on'] not in segments:
                err(f"feature {fid!r} sits on unknown segment {f['on']!r}")
            if not 0.0 <= f.get('at', -1) <= 1.0:
                err(f"feature {fid!r} has position {f.get('at')!r} outside 0..1")

    # observations
    if obs is not None:
        valid = set(segments) | set(nodes) | set(features)
        for o in obs.get('observations', []):
            if o['target'] not in valid:
                err(f"observation dated {o.get('date')} targets unknown id {o['target']!r}"
                    + (f" — that id is retired ({retired[o['target']]['reason']})"
                       if o['target'] in retired else ""))
            if not o.get('date'):
                err(f"observation on {o['target']!r} has no date — the date is what makes "
                    f"the note meaningful and must always travel with the text")

    return dict(trails=len(trails), nodes=len(nodes), segments=len(segments),
                features=len(features), retired=len(retired),
                miles=round(sum(s['miles'] for s in segments.values()), 1))


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    graph = json.load(open(sys.argv[1]))
    obs = json.load(open(sys.argv[2])) if len(sys.argv) > 2 else None
    if obs is None:
        sibling = os.path.join(os.path.dirname(sys.argv[1]), 'observations.json')
        if os.path.exists(sibling):
            obs = json.load(open(sibling))

    stats = check(graph, obs)
    print(f"{stats['trails']} trails  {stats['nodes']} nodes  {stats['segments']} segments  "
          f"{stats['features']} features  {stats['retired']} retired  {stats['miles']} mi")

    for w in warnings:
        print(f"  warn  {w}")
    for e in errors:
        print(f"  ERROR {e}")
    if errors:
        print(f"\n{len(errors)} error(s) — a build should fail here rather than ship quietly.")
        sys.exit(1)
    print(f"\nvalid{f' ({len(warnings)} warning(s))' if warnings else ''}")


if __name__ == '__main__':
    main()
