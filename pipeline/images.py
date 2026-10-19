"""Photos for tree and landmark clues, public domain only (Wikimedia Commons: Public domain / CC0 / PD-*).

Two stages, so every shipped photo is looked at by a human (or by Claude) first:

  python images.py candidates   find PD candidates for each photo slot in schedule.json, save small previews
                                to data/img_review/<slot>/ and an index at data/img_review/index.json
  python images.py fetch        download the picks listed in data/photo_picks.json at display size into
                                data/img/ and write data/photos.json (file + credit per slot)

A slot is one clue: its key is sha1(clue text)[:10]. photo_picks.json maps slot -> Commons file title.
"""
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import requests

from socrata import query

DATA = Path(__file__).resolve().parent.parent / "data"
REVIEW = DATA / "img_review"
IMG = DATA / "img"
API = "https://commons.wikimedia.org/w/api.php"
HEAD = {"User-Agent": "hood-guesser-pipeline/0.1 (https://github.com/norlovskiy/game-design-proj-6)"}
MIN_WIDTH = 1000
MAX_CANDIDATES = 8


def slot_key(text):
    return hashlib.sha1(text.encode()).hexdigest()[:10]


def is_pd(license_name):
    l = license_name.lower()
    return l.startswith("public domain") or l.startswith("cc0") or l.startswith("pd")


def thumb_url(url, width):
    """Commons thumbnail URL for an original file URL (query string stripped)."""
    base = url.split("?")[0]
    return base.replace("/commons/", "/commons/thumb/") + f"/{width}px-{base.rsplit('/', 1)[1]}"


def download(url, tries=6):
    """GET with pacing and backoff; Wikimedia rate-limits bursts of thumbnail requests."""
    for k in range(tries):
        time.sleep(1.0 + 3 * k)
        r = requests.get(url, headers=HEAD, timeout=120)
        if r.ok:
            return r.content
        if r.status_code not in (429, 503):
            return None
    return None


def commons(**params):
    r = requests.get(API, params={"action": "query", "format": "json", "prop": "imageinfo",
                                  "iiprop": "url|size|mime|extmetadata", **params}, headers=HEAD, timeout=60)
    r.raise_for_status()
    for p in (r.json().get("query", {}).get("pages", {}) or {}).values():
        ii = p["imageinfo"][0]
        m = ii.get("extmetadata", {})
        lic = m.get("LicenseShortName", {}).get("value", "")
        if ii["mime"] != "image/jpeg" or ii["width"] < MIN_WIDTH or not is_pd(lic):
            continue
        author = re.sub(r"<[^>]+>", "", m.get("Artist", {}).get("value", "")).strip() or "Unknown"
        yield {"title": p["title"], "width": ii["width"], "height": ii["height"], "license": lic, "author": author[:120],
               "page": ii["descriptionurl"], "url": ii["url"]}


def landmark_candidates(clue):
    names = [n.strip(" .") for n in clue.split(":", 1)[1].split(";")]
    found = {}
    for nm in names:
        rows = query("buis-pvji", select="latitude,longitude", where="lpc_name='%s'" % nm.replace("'", "''"), limit=1)
        toks = [t.lower() for t in re.split(r"\W+", nm) if len(t) >= 4]
        if rows:
            for c in commons(generator="geosearch", ggscoord=f"{rows[0]['latitude']}|{rows[0]['longitude']}", ggsradius=150,
                             ggsnamespace=6, ggslimit=50):
                c["subject"] = nm
                c["name_match"] = sum(t in c["title"].lower() for t in toks)
                found[c["title"]] = c
        for c in commons(generator="search", gsrsearch=f'"{nm}" New York', gsrnamespace=6, gsrlimit=20):
            c["subject"] = nm
            c["name_match"] = sum(t in c["title"].lower() for t in toks)
            if c["name_match"]:
                found.setdefault(c["title"], c)
    return sorted(found.values(), key=lambda c: (-c["name_match"], -c["width"]))[:MAX_CANDIDATES]


def species_candidates(clue):
    common = re.search(r"most (.+?) street trees", clue).group(1)
    rows = query("uvpi-gqnh", select="spc_latin", where="spc_common='%s'" % common.replace("'", "''"), limit=1)
    latin = rows[0]["spc_latin"] if rows else common
    out = {}
    for q in (f'"{latin}"', f"{latin} tree"):
        for c in commons(generator="search", gsrsearch=q, gsrnamespace=6, gsrlimit=40):
            c["subject"] = f"{common} ({latin})"
            out[c["title"]] = c
    return sorted(out.values(), key=lambda c: -c["width"])[:MAX_CANDIDATES]


def slots(schedule):
    for s in schedule:
        for t, text in zip(s["templates"], s["clues"]):
            if t == "landmark_name":
                yield slot_key(text), "landmark", text
            elif t.startswith("top") and "species:" in t:
                yield slot_key(text), "species", text


def stage_candidates():
    schedule = json.loads((DATA / "schedule.json").read_text())
    REVIEW.mkdir(exist_ok=True)
    index = {}
    for key, kind, text in slots(schedule):
        if key in index:
            continue
        cands = landmark_candidates(text) if kind == "landmark" else species_candidates(text)
        d = REVIEW / key
        d.mkdir(exist_ok=True)
        for n, c in enumerate(cands):
            if not (d / f"{n}.jpg").exists():
                data = download(thumb_url(c["url"], 500))
                if data:
                    (d / f"{n}.jpg").write_bytes(data)
            c["preview"] = f"{key}/{n}.jpg"
        index[key] = {"kind": kind, "clue": text, "candidates": cands}
        print(f"{key} {kind:8s} {len(cands)} candidates  {text[:70]}")
    (REVIEW / "index.json").write_text(json.dumps(index, indent=1))


def stage_sheets():
    """One labeled contact sheet per slot so candidates can be compared at a glance."""
    from PIL import Image, ImageDraw
    index = json.loads((REVIEW / "index.json").read_text())
    for key, v in index.items():
        cs = [c for c in v["candidates"] if (REVIEW / c["preview"]).exists()]
        if not cs:
            continue
        w, tiles = 320, []
        for n, c in enumerate(cs):
            im = Image.open(REVIEW / c["preview"]).convert("RGB")
            im.thumbnail((w, 240))
            t = Image.new("RGB", (w, 262), "white")
            t.paste(im, (0, 0))
            ImageDraw.Draw(t).text((4, 244), f"{n}: {c['title'][5:45]}", fill="black")
            tiles.append(t)
        cols = 4
        sheet = Image.new("RGB", (cols * w, ((len(tiles) + cols - 1) // cols) * 262), "white")
        for i, t in enumerate(tiles):
            sheet.paste(t, ((i % cols) * w, (i // cols) * 262))
        sheet.save(REVIEW / f"sheet_{key}.jpg", quality=80)
        print(key, v["kind"], len(cs), "|", v["clue"][-60:])


def stage_fetch():
    picks = json.loads((DATA / "photo_picks.json").read_text())
    index = json.loads((REVIEW / "index.json").read_text())
    IMG.mkdir(exist_ok=True)
    out = {}
    for key, title in picks.items():
        if not title:
            continue
        c = next(c for c in index[key]["candidates"] if c["title"] == title)
        data = download(thumb_url(c["url"], 960))
        if not data:
            sys.exit(f"could not download {title}")
        fn = f"{key}.jpg"
        (IMG / fn).write_bytes(data)
        out[key] = {"file": fn, "credit": f"{c['author']}, {c['license']}, via Wikimedia Commons", "page": c["page"]}
        print(f"{key}: {len(data) // 1024} KB  {title[:60]}")
    (DATA / "photos.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    {"candidates": stage_candidates, "sheets": stage_sheets, "fetch": stage_fetch}[sys.argv[1]]()
