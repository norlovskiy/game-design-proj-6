"""Bundle the game into dist/index.html (single self-contained file) and dist/nyclue.zip for itch.io.

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

sys.path.insert(0, str(Path(__file__).resolve().parent / "pipeline"))
import solver

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


def photo_slot(text):
    return hashlib.sha1(text.encode()).hexdigest()[:10]


NAMED = json.loads((DATA / "photo_names.json").read_text())   # species / landmark name -> file; see that file


def _entry(file_or_obj):
    o = file_or_obj if isinstance(file_or_obj, dict) else {"file": file_or_obj}
    return {"src": "img/" + o["file"], "credit": o.get("credit", "")}


def clue_photos(text, template, photos):
    """Photos for one clue: a clue-level photo (hash of the text; pipeline/images.py) plus one per named landmark or species."""
    out = []
    slot = photo_slot(text)
    if slot in photos:
        out.append({"src": "img/" + photos[slot]["file"], "credit": photos[slot]["credit"]})
    if template.startswith("landmark_name"):
        names = text.removeprefix("Landmarks here include: ").removesuffix(".").split("; ")
        out += [_entry(NAMED["landmarks"][n]) for n in names if n in NAMED["landmarks"]]
    elif ":species:" in template and template.rsplit(":", 1)[1] in NAMED["species"]:
        out.append(_entry(NAMED["species"][template.rsplit(":", 1)[1]]))
    return out


def endless_payload(photos):
    """Trimmed clue data for the in-browser generator (web/endless.js).

    Only neighborhoods with at least one acceptable combo are shipped, and only clues that appear in some acceptable
    combo (found by exhausting the solver's search). Match sets are stored once per distinct clue, as indices into `ids`.
    """
    ids = sorted(solver.CLUES)
    idx = {n: i for i, n in enumerate(ids)}
    defs, def_of, hoods = [], {}, {}
    for nta in ids:
        usable = {}
        for _, _, combo in solver.combos(nta, per_tier=10 ** 9):
            for c in combo:
                usable[id(c)] = c
        if not usable:
            continue
        entries = []
        for c in usable.values():
            key = (c["template"], c["text"])
            if key not in def_of:
                photo = clue_photos(c["text"], c["template"], photos) or 0
                def_of[key] = len(defs)
                defs.append([c["tier"], c["text"], c["template"], sorted(idx[m] for m in c["matches"]), photo])
            entries.append([def_of[key], c["quality"]])
        hoods[nta] = sorted(entries)
    return {"v": solver.RULES["data_version"], "rules": solver.RULES, "ids": ids, "defs": defs, "hoods": hoods}


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
        for i, (text, template) in enumerate(zip(s["clues"], s["templates"])):
            found = clue_photos(text, template, photos)
            if found:
                pics[i] = found
        puzzles.append({"day": s["day"], "date": s["date"], "answer": s["answer"], "clues": s["clues"], "photos": pics})
    endless = endless_payload(photos)
    html = (ROOT / "web" / "index.template.html").read_text()
    html = (html.replace("/*ENDLESS_JS*/", (ROOT / "web" / "endless.js").read_text())
                .replace("/*ENDLESS*/null", json.dumps(endless, separators=(",", ":")))
                .replace("/*SHAPES*/[]", json.dumps(shapes, separators=(",", ":")))
                .replace('"/*SCHEDULE*/"', json.dumps(obfuscate(puzzles)))
                .replace('"/*LAUNCH*/"', json.dumps(sched[0]["date"])))
    out = ROOT / "dist"
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(html)
    if "--test-date" in sys.argv:   # dist/test.html: same game pinned to a date, never zipped
        d = sys.argv[sys.argv.index("--test-date") + 1]
        (out / "test.html").write_text(html.replace("<script>\n\"use strict\";", f"<script>window.TEST_DATE={d!r};</script>\n<script>\n\"use strict\";", 1))
    used = {p["src"] for pz in puzzles for ps in pz["photos"].values() for p in ps}
    used |= {p["src"] for d in endless["defs"] if d[4] for p in d[4]}
    (out / "img").mkdir(exist_ok=True)
    for old in (out / "img").glob("*"):
        old.unlink()
    for src in used:
        (out / src).write_bytes((DATA / "img" / src.split("/")[1]).read_bytes())
    with zipfile.ZipFile(out / "nyclue.zip", "w", zipfile.ZIP_DEFLATED) as z:
        z.write(out / "index.html", "index.html")
        for src in sorted(used):
            z.write(out / src, src)
    print(f"dist/index.html {len(html)/1024:.0f} KB, {len(shapes)} shapes, {len(puzzles)} puzzles, "
          f"{len(endless['hoods'])} endless neighborhoods, {len(used)} photos, zip {(out/'nyclue.zip').stat().st_size/1024:.0f} KB")


if __name__ == "__main__":
    main()
