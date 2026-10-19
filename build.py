"""Bundle the game into dist/index.html (single self-contained file) and dist/nyc-hoods.zip for itch.io.

Projects NTA polygons to SVG paths, lightly obfuscates the schedule (XOR + base64), inlines both.
usage: .venv/bin/python build.py
"""
import base64
import hashlib
import datetime as dt
import json
import math
import sys
import zipfile
from pathlib import Path

from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
KEY = b"nyc-hoods"
TOLERANCE = 0.00025   # degrees (~25 m); keeps shapes recognisable, keeps the bundle small
SCALE = 100000        # SVG units per degree of latitude


def project(lon, lat, lat0=40.7):
    return round((lon + 74.0) * math.cos(math.radians(lat0)) * SCALE), round((40.95 - lat) * SCALE)


def path_d(geom):
    polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    parts = []
    for p in polys:
        for ring in [p.exterior, *p.interiors]:
            pts = [project(x, y) for x, y in ring.coords]
            parts.append("M" + "L".join(f"{x} {y}" for x, y in pts) + "Z")
    return "".join(parts)


def obfuscate(obj):
    raw = json.dumps(obj, separators=(",", ":")).encode()
    return base64.b64encode(bytes(b ^ KEY[i % len(KEY)] for i, b in enumerate(raw))).decode()


def main():
    ntas = json.loads((DATA / "ntas.json").read_text())
    sched = json.loads((DATA / "schedule.json").read_text())
    shapes = []
    for n in ntas:
        g = shape(n["geometry"]).simplify(TOLERANCE, preserve_topology=True)
        if g.is_empty:
            continue
        c = g.centroid
        shapes.append({"id": n["id"], "name": n["name"], "boro": n["borough"], "type": n["type"], "d": path_d(g),
                       "c": list(project(c.x, c.y))})   # centroid in SVG units, for guess-distance feedback
    photos_file = DATA / "photos.json"
    photos = json.loads(photos_file.read_text()) if photos_file.exists() else {}   # slot -> {file, credit}; see pipeline/images.py
    puzzles = []
    for s in sched:
        pics = {}
        for i, text in enumerate(s["clues"]):
            slot = hashlib.sha1(text.encode()).hexdigest()[:10]
            if slot in photos:
                pics[i] = {"src": "img/" + photos[slot]["file"], "credit": photos[slot]["credit"]}
        puzzles.append({"day": s["day"], "date": s["date"], "answer": s["answer"], "clues": s["clues"], "photos": pics})
    html = (ROOT / "web" / "index.template.html").read_text()
    html = (html.replace("/*SHAPES*/[]", json.dumps(shapes, separators=(",", ":")))
                .replace('"/*SCHEDULE*/"', json.dumps(obfuscate(puzzles)))
                .replace('"/*LAUNCH*/"', json.dumps(sched[0]["date"])))
    out = ROOT / "dist"
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(html)
    if "--test-date" in sys.argv:   # dist/test.html: same game pinned to a date, never zipped
        d = sys.argv[sys.argv.index("--test-date") + 1]
        (out / "test.html").write_text(html.replace("<script>\n\"use strict\";", f"<script>window.TEST_DATE={d!r};</script>\n<script>\n\"use strict\";", 1))
    used = {p["src"] for pz in puzzles for p in pz["photos"].values()}
    (out / "img").mkdir(exist_ok=True)
    for old in (out / "img").glob("*.jpg"):
        old.unlink()
    for src in used:
        (out / src).write_bytes((DATA / "img" / src.split("/")[1]).read_bytes())
    with zipfile.ZipFile(out / "nyc-hoods.zip", "w", zipfile.ZIP_DEFLATED) as z:
        z.write(out / "index.html", "index.html")
        for src in sorted(used):
            z.write(out / src, src)
    print(f"dist/index.html {len(html)/1024:.0f} KB, {len(shapes)} shapes, {len(puzzles)} puzzles, "
          f"{len(used)} photos, zip {(out/'nyc-hoods.zip').stat().st_size/1024:.0f} KB")


if __name__ == "__main__":
    main()
