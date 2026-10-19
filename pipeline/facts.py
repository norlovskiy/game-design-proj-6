"""Turn data/metrics.json into candidate clues per residential NTA -> data/clues.json.

A clue is {template, tier, text, score}. Lower score = more distinctive (rank distance
from the nearest extreme of the 197 residential neighborhoods). Text is built only from
computed values, never free-written.
"""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
SQFT_PER_KM2 = 10_763_910.4
MAX_SCORE = 40          # a clue must sit within 40 places (top/bottom ~20%) of an extreme to count as distinctive

ntas = json.loads((DATA / "ntas.json").read_text())
raw = json.loads((DATA / "metrics.json").read_text())
metrics, labels = raw["metrics"], raw["labels"]

from shapely.geometry import shape
from shapely.ops import transform
import pyproj

_to_ft = pyproj.Transformer.from_crs(4326, 2263, always_xy=True).transform
RES = [n for n in ntas if n["type"] == "0"]
AREA = {n["id"]: transform(_to_ft, shape(n["geometry"])).area / SQFT_PER_KM2 for n in RES}
N = len(RES)

# (metric key, tier, noun phrase for "per km²" density clues)
DENSITY = [
    ("311:Noise - Helicopter", 1, "helicopter noise complaints"),
    ("311:Lost Property", 1, "lost-property reports to 311"),
    ("311:Unsanitary Pigeon Condition", 1, "pigeon-nuisance complaints"),
    ("311:Urinating in Public", 1, "public-urination complaints"),
    ("311:Unleashed Dog", 1, "unleashed-dog complaints"),
    ("311:Abandoned Bike", 1, "abandoned-bike reports"),
    ("311:Noise - House of Worship", 1, "house-of-worship noise complaints"),
    ("311:Illegal Fireworks", 2, "illegal-fireworks complaints"),
    ("311:Dead Animal", 2, "dead-animal reports"),
    ("311:Taxi Complaint", 2, "taxi complaints"),
    ("311:Graffiti", 2, "graffiti complaints"),
    ("311:Panhandling", 2, "panhandling complaints"),
    ("311:Noise - Park", 2, "park-noise complaints"),
    ("311:Cannabis Retailer", 2, "cannabis-retailer complaints"),
    ("311:Mobile Food Vendor", 2, "mobile-food-vendor complaints"),
    ("311:Outdoor Dining", 2, "outdoor-dining complaints"),
    ("311:Drinking", 2, "public-drinking complaints"),
    ("311:Animal in a Park", 2, "animal-in-a-park reports"),
    ("311:Dead/Dying Tree", 2, "dead-or-dying-tree reports"),
    ("311:Rodent", 2, "rodent complaints"),
    ("rat_signs", 2, "rodent inspections that failed for rat activity"),
    ("hydrants", 2, "fire hydrants"),
    ("street_trees", 3, "street trees"),
    ("restaurants", 3, "restaurants"),
    ("landmarks", 3, "individually landmarked sites"),
    ("subway_stations", 3, "subway stations"),
]
CUISINE_TIER = 1


def ranks(values):
    """values: {id: number} over all RES. Returns {id: rank} where 1 = highest."""
    order = sorted(values, key=lambda i: (-values[i], i))
    return {i: r + 1 for r, i in enumerate(order)}


def ordinal(n):
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def density_clues(out):
    for key, tier, noun in DENSITY:
        m = metrics.get(key, {})
        dens = {n["id"]: m.get(n["id"], 0) / AREA[n["id"]] for n in RES}
        rk = ranks(dens)
        for i, r in rk.items():
            if m.get(i, 0) < 10:   # tiny counts are noise, not signal
                continue
            score = min(r - 1, N - r)
            if score > MAX_SCORE:
                continue
            if r == 1:
                text = f"Per square kilometre, it has more {noun} than any other residential neighborhood in NYC."
            elif r <= 10:
                text = f"Per square kilometre, it has the {ordinal(r)}-most {noun} of NYC's {N} residential neighborhoods."
            elif r <= N // 2:
                pct = -(-100 * r // N // 5) * 5
                text = f"Per square kilometre, it is in the top {pct}% of NYC's residential neighborhoods for {noun}."
            elif N - r + 1 <= 10:
                text = f"Per square kilometre, it has the {ordinal(N - r + 1)}-fewest {noun} of NYC's {N} residential neighborhoods."
            else:
                pct = -(-100 * (N - r + 1) // N // 5) * 5
                text = f"Per square kilometre, it is in the bottom {pct}% of NYC's residential neighborhoods for {noun}."
            if r > N // 2:
                score += 15   # prefer 'most' clues over 'fewest' clues
            out[i].append({"template": key, "tier": tier, "text": text, "score": score})


def cuisine_clues(out):
    for key, m in metrics.items():
        if not key.startswith("cuisine:"):
            continue
        cuisine, total = key.split(":")[1], sum(m.values())
        if total < 8:
            continue
        for n in RES:
            k = m.get(n["id"], 0)
            share = k / total
            # distinctive if the neighborhood holds a large share of the city's restaurants of this cuisine
            if k >= 3 and share >= 0.12:
                out[n["id"]].append({"template": key, "tier": CUISINE_TIER,
                                     "text": f"{k} of NYC's {total} {cuisine} restaurants are here.",
                                     "score": round(10 * (1 - share), 2)})


def tree_clues(out):
    for i, s in labels["tree_species"].items():
        if i in AREA and s["signature"]:
            out[i].append({"template": "tree_signature", "tier": 1,
                           "text": f"Its street trees are unusually rich in {s['signature'].title()}.",
                           "score": 6})


def landmark_clues(out):
    for i, names in labels["landmark_names"].items():
        if i in AREA and len(names) >= 1:
            out[i].append({"template": "landmark_name", "tier": 5,
                           "text": "Landmarks here include: " + "; ".join(sorted(set(names))[:3]) + ".",
                           "score": 5 + len(names)})


def subway_clues(out):
    for i, st in labels["subway"].items():
        if i in AREA:
            routes = sorted({r for s in st for r in s["routes"]})
            out[i].append({"template": "subway_lines", "tier": 5,
                           "text": "Subway lines serving it: " + ", ".join(routes) + ".",
                           "score": 4 if len(routes) <= 6 else 6})


def main():
    out = {n["id"]: [] for n in RES}
    density_clues(out); cuisine_clues(out); tree_clues(out); landmark_clues(out); subway_clues(out)
    # name-leak check: no clue may contain a >=4-letter token of its own neighborhood's name
    for n in RES:
        toks = {t.lower() for t in n["name"].replace("-", " ").replace("/", " ").split() if len(t) >= 4}
        out[n["id"]] = [c for c in out[n["id"]] if not any(t in c["text"].lower() for t in toks)]
        out[n["id"]].sort(key=lambda c: c["score"])
    (DATA / "clues.json").write_text(json.dumps(out, indent=1))
    full = [n["id"] for n in RES if all(any(c["tier"] == t for c in out[n["id"]]) for t in (1, 2, 3, 5))]
    print(f"{len(full)}/{N} neighborhoods have a clue in every tier (1,2,3,5)")
    for t in (1, 2, 3, 5):
        print(" tier", t, "covered:", sum(1 for n in RES if any(c["tier"] == t for c in out[n["id"]])))


if __name__ == "__main__":
    main()
