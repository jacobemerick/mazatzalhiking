#!/usr/bin/env python3
"""Keep the trail markdown in step with the graph (#18, #30).

    ./tools/sync_trails.py           # add what is missing, report what drifted
    ./tools/sync_trails.py --fix     # also rewrite leg headings to the graph's names
    ./tools/sync_trails.py --check   # report only; exit 1 if anything is missing or drifted

`content/trails/<slug>.md` is authored: Jacob's condition notes live there and nothing
here ever changes a note. What this tool owns is the skeleton around them -- that
every trail has a file, that every leg has a `## name {#id}` section in walking order,
and that the heading text matches the leg's name in the graph. A new leg in the graph
gets an empty section appended; a leg that leaves the graph is reported, not deleted,
because its notes are still Jacob's words.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import validate_graph as V
import observations as O
from trails import order_legs

CONTENT = os.path.join(ROOT, 'content', 'trails')
GRAPH = os.path.join(ROOT, 'curation', 'graph.json')
FIX = '--fix' in sys.argv
CHECK = '--check' in sys.argv

SECTION = re.compile(r'^##\s+(?P<name>.*?)\s*\{#(?P<id>[A-Za-z]+:)?(?P<code>[0-9A-Za-z]{2,4})\}\s*$', re.M)


def leg_heading(seg, nodes, rev):
    """The leg's name without the trail prefix the graph gives it, e.g.
    'Barnhardt Trailhead to Sandy Saddle' -- the page already says which trail."""
    name = seg['name']
    m = re.match(r'^(.*?) from (.*)$', name)
    return m.group(2) if m else name


def front_matter(trail):
    return f'---\ntitle: "{trail["name"]}"\ntrail: "{trail["id"]}"\n---\n'


def main():
    graph = json.load(open(GRAPH))
    nodes = {n['id']: n for n in graph['nodes']}
    os.makedirs(CONTENT, exist_ok=True)
    problems = 0
    changed = []

    for t in graph['trails']:
        legs = order_legs(t['id'], graph['segments'], nodes)
        path = os.path.join(CONTENT, f"{t['slug']}.md")
        if not os.path.exists(path):
            body = front_matter(t) + '\n' + ''.join(
                f"## {leg_heading(s, nodes, r)} {{#{s['id']}}}\n\n" for s, r in legs)
            if not CHECK:
                open(path, 'w').write(body)
            changed.append(f"created {os.path.relpath(path, ROOT)}")
            continue

        text = open(path).read()
        found = {}
        for m in SECTION.finditer(text):
            kind = (m.group('id') or 'segment:').rstrip(':')
            found[f"{kind}:{m.group('code')}"] = m
        want = {f"segment:{s['id']}": (s, r) for s, r in legs}

        # unknown segment sections: notes on a leg the graph no longer has
        for key in found:
            kind, code = key.split(':')
            if kind == 'segment' and key not in want:
                if code in {s['id'] for s in graph['segments']}:
                    print(f"  warn  {t['slug']}.md: section {{#{code}}} is a leg of a different trail")
                else:
                    print(f"  ERROR {t['slug']}.md: section {{#{code}}} is not a segment in the graph"
                          + (f" (retired: {next(r['reason'] for r in graph['retired'] if r['id']==code)})"
                             if any(r['id'] == code for r in graph['retired']) else ''))
                    problems += 1
            if kind == 'node' and code not in nodes:
                print(f"  ERROR {t['slug']}.md: section {{#node:{code}}} is not a node in the graph")
                problems += 1

        # missing legs get an empty section at the end
        missing = [(s, r) for key, (s, r) in want.items() if key not in found]
        new_text = text
        if missing:
            add = ''.join(f"\n## {leg_heading(s, nodes, r)} {{#{s['id']}}}\n" for s, r in missing)
            new_text = new_text.rstrip('\n') + '\n' + add
            changed.append(f"{t['slug']}.md: added {', '.join(s['id'] for s, _ in missing)}")

        # heading drift
        for key, (s, r) in want.items():
            m = found.get(key)
            if m and m.group('name') != leg_heading(s, nodes, r):
                if FIX:
                    new_text = new_text.replace(m.group(0), f"## {leg_heading(s, nodes, r)} {{#{s['id']}}}")
                    changed.append(f"{t['slug']}.md: renamed {s['id']}")
                else:
                    print(f"  warn  {t['slug']}.md: heading for {s['id']} is {m.group('name')!r}, "
                          f"graph says {leg_heading(s, nodes, r)!r} (--fix rewrites it)")
                    if CHECK:
                        problems += 1

        # the file must still parse
        try:
            O.parse(new_text.split('\n---\n', 1)[-1] if new_text.startswith('---\n') else new_text, path)
        except O.ParseError as e:
            print(f"  ERROR {e}")
            problems += 1

        if new_text != text and not CHECK:
            open(path, 'w').write(new_text)

    for w in V.warnings:
        print(f"  warn  {w}")
    for c in changed:
        print(('  would ' if CHECK else '  ') + c)
    if problems:
        sys.exit(f"{problems} problem(s)")
    if CHECK and changed:
        sys.exit(1)
    print("content/trails is in step with the graph" if not changed else f"{len(changed)} change(s)")


if __name__ == '__main__':
    main()
