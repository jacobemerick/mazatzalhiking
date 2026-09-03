#!/usr/bin/env python3
"""Elevation: the gain algorithm, and the DEM the numbers come from (#12).

Gain and loss are derived from USGS 3DEP resampled along the cleaned geometry, at a
3 m threshold. Recorded device elevation stays in the archive and is not published:
it is unbiased but noisy, and gain is a rectified sum, so noise can only inflate it.

`profile_gain_loss` implements schema decision 3 -- simplify the elevation profile
first, then sum -- which makes gain forward exactly loss backward, so one pair of
numbers covers both directions of a segment.

`sample` reads 3DEP through the USGS ImageServer and caches every value to
archive/dem-3dep.json, so rebuilding the committed tree needs no network.

Rationale and the measurements behind it: docs/elevation.md
"""
import json, os, time, urllib.parse, urllib.request

THRESHOLD_M = 3.0

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
CACHE = os.path.join(ROOT, 'archive', 'dem-3dep.json')
SERVICE = ("https://elevation.nationalmap.gov/arcgis/rest/services/"
           "3DEPElevation/ImageServer/getSamples")
BATCH = 400


def profile_gain_loss(eles, threshold_m=THRESHOLD_M):
    """Gain and loss, direction-symmetric: simplify the profile, then sum.

    Reversing the input swaps the two results exactly, which is what lets a segment
    store one pair of numbers for both directions."""
    e = [x for x in eles if x is not None]
    if len(e) < 2:
        return 0.0, 0.0
    ext = [e[0]]
    for v in e[1:]:
        if len(ext) < 2:
            if v != ext[-1]:
                ext.append(v)
            continue
        up_prev = ext[-1] > ext[-2]
        up_now = v > ext[-1]
        if v == ext[-1]:
            continue
        if up_now == up_prev:
            ext[-1] = v            # extend the run
        else:
            ext.append(v)          # direction changed
    while len(ext) > 2:
        runs = [(abs(ext[i+1] - ext[i]), i) for i in range(len(ext) - 1)]
        interior = [(m, i) for m, i in runs if 0 < i < len(ext) - 2]
        if not interior:
            break
        m, i = min(interior)
        if m >= threshold_m:
            break
        del ext[i:i+2]             # drop the reversal, neighbours merge
        merged = [ext[0]]
        for v in ext[1:]:
            if len(merged) >= 2 and (v > merged[-1]) == (merged[-1] > merged[-2]):
                merged[-1] = v
            elif v != merged[-1]:
                merged.append(v)
        ext = merged
    gain = sum(max(0.0, ext[i+1] - ext[i]) for i in range(len(ext) - 1))
    loss = sum(max(0.0, ext[i] - ext[i+1]) for i in range(len(ext) - 1))
    return gain, loss


# ------------------------------------------------------------------- DEM ----

def key(lon, lat):
    return f'{lon:.6f},{lat:.6f}'


def load_cache():
    return json.load(open(CACHE)) if os.path.exists(CACHE) else {}


def save_cache(cache):
    tmp = CACHE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(cache, f, separators=(',', ':'), sort_keys=True)
    os.replace(tmp, CACHE)          # atomic: an interrupted save cannot truncate


def _fetch(points):
    geom = {'points': [[x, y] for x, y in points], 'spatialReference': {'wkid': 4326}}
    body = urllib.parse.urlencode({
        'geometry': json.dumps(geom), 'geometryType': 'esriGeometryMultipoint',
        'returnFirstValueOnly': 'true',
        'interpolation': 'RSP_BilinearInterpolation', 'f': 'json'}).encode()
    last = None
    for attempt in range(4):
        try:
            r = json.load(urllib.request.urlopen(
                urllib.request.Request(SERVICE, body), timeout=180))
            if 'samples' in r:
                return r['samples']
            last = RuntimeError(str(r)[:200])
        except Exception as e:                      # transient service failures
            last = e
        time.sleep(2 * (attempt + 1))
    raise last


def sample(coords, cache=None, progress=None):
    """Elevation in metres for [(lon, lat), ...]. Cached on disk, so only the
    coordinates that have never been asked for cost a request."""
    cache = load_cache() if cache is None else cache
    want, seen = [], set()
    for lon, lat in coords:
        k = key(lon, lat)
        if k not in cache and k not in seen:
            seen.add(k); want.append((lon, lat))
    for i in range(0, len(want), BATCH):
        for s in _fetch(want[i:i+BATCH]):
            loc = s.get('location') or {}
            try:
                v = float(s.get('value'))
            except (TypeError, ValueError):
                v = None
            cache[key(loc['x'], loc['y'])] = v
        save_cache(cache)
        if progress:
            progress(min(i + BATCH, len(want)), len(want))
    return [cache.get(key(lon, lat)) for lon, lat in coords], cache
