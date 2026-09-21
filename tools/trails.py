"""Shared trail helpers: which legs make up a trail, and in what order."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import validate_graph as V


def order_legs(trail_id, segments, nodes):
    """Chain a trail's legs into walking order. Returns [(segment, reversed), ...].

    Starts at a trailhead when exactly one end is one, otherwise at the lower end
    (trails are conventionally read bottom-up). A leg that starts and ends at the
    same node (the Saddle Mountain Mine Loop) is listed right after the leg that
    arrives at that node. Any other non-path shape warns and falls back to file
    order, so a curation change cannot silently misorder a page.
    """
    legs = [s for s in segments if trail_id in s['trails']]
    loops = [s for s in legs if s['from'] == s['to']]
    path = [s for s in legs if s['from'] != s['to']]
    if not path:
        return [(s, False) for s in legs]
    adj = {}
    for s in path:
        adj.setdefault(s['from'], []).append(s)
        adj.setdefault(s['to'], []).append(s)
    ends = [n for n, ss in adj.items() if len(ss) == 1]
    if len(ends) != 2 or any(len(ss) > 2 for ss in adj.values()):
        V.warn(f"trail {trail_id!r}: legs do not form a single path; listing them in file order")
        return [(s, False) for s in legs]

    def rank(nid):
        n = nodes[nid]
        return (0 if n['kind'] == 'trailhead' else 1, n.get('ele_ft') or 0, nid)
    start = min(ends, key=rank)
    out, at, used = [], start, set()
    while True:
        nxt = [s for s in adj.get(at, []) if s['id'] not in used]
        if not nxt:
            break
        s = nxt[0]
        used.add(s['id'])
        rev = s['to'] == at
        out.append((s, rev))
        at = s['from'] if rev else s['to']
        for lp in loops:
            if lp['from'] == at and lp['id'] not in used:
                used.add(lp['id'])
                out.append((lp, False))
    return out


def leg_figures(seg, rev):
    """(from node, to node, gain, loss) for the direction the leg is read in."""
    gain, loss = (seg['loss_ft'], seg['gain_ft']) if rev else (seg['gain_ft'], seg['loss_ft'])
    a, b = (seg['to'], seg['from']) if rev else (seg['from'], seg['to'])
    return a, b, gain, loss
