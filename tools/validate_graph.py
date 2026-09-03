#!/usr/bin/env python3
"""Structural validation for a trail graph instance.

    ./tools/validate_graph.py schema/example/graph.json [observations.json]

The observations file defaults to the sibling observations.json when one exists.

Checks the invariants that matter for correctness rather than mere shape: that
references resolve, that the network is actually connected, and that retired ids
stay retired. Exits non-zero on any error, so a build can gate on it.

This is the seed of the validation #16 asks for, not its completion — #16 still has
to check total network mileage against the corpus inventory and wire this into the
build. Written against the stdlib so it runs anywhere with no install step.
"""
import json, sys, os, re, pathlib
from datetime import date
from collections import defaultdict

errors, warnings = [], []


def err(m):
    errors.append(m)


def warn(m):
    warnings.append(m)


def check(graph, obs=None, obs_path=None):
    trails = {t['id']: t for t in graph.get('trails', [])}
    nodes = {n['id']: n for n in graph.get('nodes', [])}
    segments = {s['id']: s for s in graph.get('segments', [])}
    features = {f['id']: f for f in graph.get('features', [])}
    retired = {r['id']: r for r in graph.get('retired', [])}

    # duplicate ids within each space
    for label, items in (('trail', graph.get('trails', [])), ('node', graph.get('nodes', [])),
                         ('segment', graph.get('segments', [])), ('feature', graph.get('features', []))):
        seen, folded = set(), {}
        for it in items:
            if it['id'] in seen:
                err(f"duplicate {label} id {it['id']!r}")
            seen.add(it['id'])
            # Ids are case-sensitive, but a segment's geometry lives at geometry/<id>.json
            # and case-insensitive filesystems collapse 0A and 0a onto one file, silently
            # destroying the older line. That is a segment-only data loss, but the rule is
            # enforced on every kind so the id space reads the same way everywhere and a
            # graph stays portable rather than depending on where it was authored.
            k = it['id'].lower()
            if k in folded and folded[k] != it['id']:
                err(f"{label} ids {folded[k]!r} and {it['id']!r} differ only in case"
                    + (" — their geometry files collide on a case-insensitive filesystem"
                       if label == 'segment' else
                       " — ids must be unique regardless of case"))
            folded[k] = it['id']

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
        # A leg that returns to its own junction is legitimate but rare -- a spur of tread
        # that loops back rather than dead-ending, where no node belongs partway round
        # because there is nothing to turn onto. Warn rather than reject, so it gets a
        # human look without the graph having to lie about the ground.
        if s['from'] == s['to']:
            warn(f"segment {sid!r} ({s['name']!r}) starts and ends at node {s['from']!r} — "
                 f"fine for tread that genuinely loops back, wrong if the far endpoint was "
                 f"meant to be a different node")
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
        # A split is an error unless it has been declared. Almost every split is a missed
        # junction; a genuine one — a trailhead reached only by water, say — is real
        # geography and gets recorded in the graph rather than silencing the check.
        declared = {frozenset(i['nodes']): i for i in graph.get('islands', [])}
        matched = set()
        if len(components) > 1:
            components.sort(key=len, reverse=True)
            undeclared = []
            for c in components[1:]:
                key = frozenset(c)
                if key in declared:
                    matched.add(key)
                    warn(f"island (declared {declared[key]['on']}): "
                         f"{', '.join(sorted(nodes[n]['name'] for n in c))} — "
                         f"{declared[key]['reason']}")
                else:
                    undeclared.append(c)
            if undeclared:
                err(f"network splits into {len(components)} components "
                    f"(largest {len(components[0])} nodes), {len(undeclared)} of them "
                    f"undeclared; a route cannot cross between them")
                for c in undeclared:
                    err(f"  stranded: {', '.join(sorted(nodes[n]['name'] for n in c))}")
        for key, i in declared.items():
            if key not in matched:
                unknown = [n for n in key if n not in nodes]
                err(f"islands entry dated {i['on']} does not match any isolated component"
                    + (f" — unknown node(s) {', '.join(sorted(unknown))}" if unknown else
                       " — those nodes are connected to the rest of the network, or the "
                       "component has changed and needs re-reviewing"))

    # features
    for fid, f in features.items():
        if 'on' in f:
            if f['on'] not in segments:
                err(f"feature {fid!r} sits on unknown segment {f['on']!r}")
            if not 0.0 <= f.get('at', -1) <= 1.0:
                err(f"feature {fid!r} has position {f.get('at')!r} outside 0..1")

    # observations
    if obs is not None:
        check_observations(obs, segments, nodes, features, retired, obs_path)

    return dict(trails=len(trails), nodes=len(nodes), segments=len(segments),
                features=len(features), retired=len(retired),
                observations=len(obs.get('observations', [])) if obs is not None else None,
                miles=round(sum(s['miles'] for s in segments.values()), 1))


OBS_CATEGORIES = ('brush', 'deadfall', 'tread', 'route-finding', 'water', 'access')
OBS_TARGET = re.compile(r'^(segment|node|feature):([0-9A-Za-z]{2,4})$')
OBS_DATE = re.compile(r'^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$')
OBS_PHOTO = re.compile(r'^[^/\\\\]+\.(jpe?g|png|webp)$')


def check_observations(obs, segments, nodes, features, retired, obs_path=None):
    """The rules in schema/observations.schema.json, re-checked here because this
    tool is stdlib-only and does not run a JSON Schema validator. The ones that
    need the graph -- does the target exist, in the right id space -- can only
    live here anyway."""
    spaces = {'segment': segments, 'node': nodes, 'feature': features}
    # Placeholder text is fine in schema/example, which exists to be invented. In a
    # real instance it is fabricated trail advice under Jacob's name, so refuse it.
    example = obs_path is not None and 'example' in pathlib.Path(obs_path).parts
    photos_seen = {}
    for i, o in enumerate(obs.get('observations', [])):
        where = f"observation #{i} ({o.get('target')!r}, {o.get('date')!r})"
        m = OBS_TARGET.match(str(o.get('target', '')))
        if not m:
            err(f"{where}: target must be '<kind>:<id>' with kind segment, node or "
                f"feature -- a bare id is ambiguous because node and segment ids overlap, "
                f"and a trail is not a target: write the note against its legs")
        else:
            kind, tid = m.groups()
            if tid not in spaces[kind]:
                err(f"{where}: no {kind} with id {tid!r}"
                    + (f" -- that id is retired ({retired[tid]['reason']}); re-target the "
                       f"note onto {', '.join(retired[tid].get('superseded_by', [])) or 'its successor'}"
                       if kind == 'segment' and tid in retired else ""))
        d = o.get('date')
        if not d or not OBS_DATE.match(str(d)):
            err(f"{where}: date must be a full YYYY-MM-DD -- the date is what makes the "
                f"note meaningful and must always travel with the text")
        elif str(d) > date.today().isoformat():
            err(f"{where}: date is in the future")
        if o.get('category') not in OBS_CATEGORIES:
            err(f"{where}: category {o.get('category')!r} is not one of "
                f"{', '.join(OBS_CATEGORIES)}")
        text = o.get('text')
        if not isinstance(text, str) or not text.strip():
            err(f"{where}: empty text -- an observation with nothing to say should not exist")
        elif 'PLACEHOLDER' in text and not example:
            err(f"{where}: placeholder text in a real instance -- every word here is "
                f"published as trail advice and must be Jacob's")
        for k in o:
            if k not in ('target', 'date', 'category', 'text', 'source', 'photos'):
                err(f"{where}: unknown field {k!r}")
        photos = o.get('photos')
        if photos is not None:
            if not isinstance(photos, list) or not photos:
                err(f"{where}: photos must be a non-empty list, or omitted")
            else:
                for ph in photos:
                    f = ph.get('file', '') if isinstance(ph, dict) else ''
                    if not OBS_PHOTO.match(str(f)):
                        err(f"{where}: photo file {f!r} must be a bare basename ending "
                            f"in .jpg, .jpeg, .png or .webp")
                    elif f in photos_seen:
                        warn(f"{where}: photo {f!r} is also attached to "
                             f"{photos_seen[f]} -- one photo shows one dated condition")
                    else:
                        photos_seen[f] = where


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    graph = json.load(open(sys.argv[1]))
    obs_path = sys.argv[2] if len(sys.argv) > 2 else None
    if obs_path is None:
        sibling = os.path.join(os.path.dirname(sys.argv[1]), 'observations.json')
        if os.path.exists(sibling):
            obs_path = sibling
    obs = json.load(open(obs_path)) if obs_path else None

    stats = check(graph, obs, obs_path)
    print(f"{stats['trails']} trails  {stats['nodes']} nodes  {stats['segments']} segments  "
          f"{stats['features']} features  {stats['retired']} retired  {stats['miles']} mi"
          + (f"  {stats['observations']} observations" if obs is not None else ""))

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
