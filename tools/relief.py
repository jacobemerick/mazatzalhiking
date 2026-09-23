"""Terrain shading behind the landing page map.

Fetches a hillshade of the map's extent from USGS 3DEP (the same public elevation
surface tools/elevation.py samples) and turns it into a light-only layer: sunlit
slopes become sand-coloured alpha, shadows and flats go transparent, and the edges
fade out so the image has no hard rectangle on the dark page.

    python3 tools/relief.py

Writes static/img/relief.webp and static/img/relief.json (the lon/lat bounds the
image covers, which layouts/partials/home/map.html reads to place it). Both are
committed: this is run by hand when the map's extent changes, not on every build.
"""
import io, json, math, urllib.parse, urllib.request
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SERVICE = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
MARGIN = 0.03          # degrees beyond the map's extent, so the fade happens off the lines
WIDTH = 640            # px; soft is fine for a background, and it keeps the file small
SAND = (250, 246, 239)


def extent():
    segs = json.loads((ROOT / "static/data/display.json").read_text())["segments"]
    pts = [(lat, lon) for s in segs.values() for lat, lon in s]
    wild = json.loads((ROOT / "archive/usfs-wilderness-boundary.geojson").read_text())
    for ring in wild["features"][0]["geometry"]["coordinates"]:
        pts += [(lat, lon) for lon, lat in ring]
    lats, lons = [p[0] for p in pts], [p[1] for p in pts]
    return (min(lons) - MARGIN, min(lats) - MARGIN, max(lons) + MARGIN, max(lats) + MARGIN)


def main():
    w, s, e, n = extent()
    height = round(WIDTH * (n - s) / ((e - w) * math.cos(math.radians(34))))
    q = urllib.parse.urlencode({
        "bbox": f"{w},{s},{e},{n}", "bboxSR": 4326, "imageSR": 4326,
        "size": f"{WIDTH},{height}", "format": "png", "f": "image",
        "renderingRule": json.dumps({"rasterFunction": "Hillshade Gray"}),
    })
    with urllib.request.urlopen(f"{SERVICE}?{q}", timeout=120) as r:
        shade = Image.open(io.BytesIO(r.read())).convert("L")

    # Fade out towards a rounded-rectangle edge (a superellipse), finishing well
    # inside the image so the map's own frame never cuts it into a hard line.
    alpha = Image.new("L", shade.size)
    px, out = shade.load(), alpha.load()
    cx, cy = (shade.width - 1) / 2, (shade.height - 1) / 2
    for y in range(shade.height):
        for x in range(shade.width):
            lit = max(0.0, min(1.0, (px[x, y] - 150) / 105)) ** 1.4   # flat ground ~180 of 255
            r = (((x - cx) / cx) ** 4 + ((y - cy) / cy) ** 4) ** 0.25
            t = max(0.0, min(1.0, (0.92 - r) / 0.22))
            out[x, y] = round(255 * lit * t * t * (3 - 2 * t))       # smoothstep
    img = Image.new("RGBA", shade.size, SAND + (0,))
    img.putalpha(alpha)
    (ROOT / "static/img").mkdir(exist_ok=True)
    img.save(ROOT / "static/img/relief.webp", "WEBP", quality=50, alpha_quality=35, method=6)
    (ROOT / "static/img/relief.json").write_text(json.dumps(
        {"west": w, "south": s, "east": e, "north": n,
         "source": "USGS 3DEP, Hillshade Gray", "width": WIDTH, "height": height}, indent=2) + "\n")
    print(f"relief.webp {WIDTH}x{height}, {(ROOT / 'static/img/relief.webp').stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
