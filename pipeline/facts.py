"""Generate candidate clues per residential NTA -> data/clues.json.

Every clue records `matches`: the ids of all residential NTAs for which its claim is true.
The solver uses these sets to measure how much each clue (and each combination) narrows the answer.

Tiers:
  1  tight   "one of the 5 neighborhoods with the most X", or compound "bottom quartile for A, B and C"
  2  broad   density bands (top/bottom 20%) and "one of the 20 neighborhoods with the most X"
  3  demographics (ACS), stated as thresholds ("median household income over $130,000")
  4  borough
  5  clincher: subway lines or landmark names
Text is built only from computed values; no free-written statistics.
"""
import itertools
import json
import math
from pathlib import Path

import pyproj
from shapely.geometry import shape
from shapely.ops import transform

DATA = Path(__file__).resolve().parent.parent / "data"
SQFT_PER_KM2 = 10_763_910.4
TOP_TIGHT, TOP_BROAD = 5, 20
MIN_POP_PER_CAPITA = 5000

ntas = json.loads((DATA / "ntas.json").read_text())
raw = json.loads((DATA / "metrics.json").read_text())
metrics, labels = raw["metrics"], raw["labels"]
demo = json.loads((DATA / "demographics.json").read_text())

_to_ft = pyproj.Transformer.from_crs(4326, 2263, always_xy=True).transform
RES = [n for n in ntas if n["type"] == "0" and n["id"] in demo]
IDS = [n["id"] for n in RES]
N = len(RES)
BORO = {n["id"]: n["borough"] for n in RES}
AREA = {n["id"]: transform(_to_ft, shape(n["geometry"])).area / SQFT_PER_KM2 for n in RES}
POP = {i: demo[i]["pop"] for i in IDS}

# ---------------------------------------------------------------- metric registry
# weight = how reasonable it is for a knowledgeable New Yorker to reason toward the answer (1 low .. 3 high)
COUNT_NOUNS = {   # absolute counts of amenities
    "count:public_art": ("public artworks", 3), "count:temp_art": ("temporary art installations", 2),
    "count:farmers_markets": ("farmers markets", 2), "count:firehouses": ("firehouses", 2),
    "count:parking_meters": ("parking meters", 2), "count:public_restrooms": ("public restrooms", 1),
    "count:wifi_hotspots": ("public Wi-Fi hotspots", 1), "count:hotels": ("hotels", 3),
    "count:bike_parking": ("bike-parking racks", 1), "count:cultural_orgs": ("cultural organizations", 3),
    "count:pops": ("privately owned public spaces", 3), "count:community_gardens": ("community gardens", 3),
    "count:bus_shelters": ("bus shelters", 1), "count:computer_centers": ("public computer centers", 1),
    "count:dog_runs": ("dog runs", 3), "landmarks": ("individually landmarked buildings", 3),
    "subway_stations": ("subway stations", 2),
}
PER1K_WEIGHTS = {"311:Noise - Helicopter": 3, "311:Illegal Fireworks": 2, "311:Cannabis Retailer": 3, "311:Outdoor Dining": 2,
                 "311:Noise - Park": 2, "311:Panhandling": 2, "311:Taxi Complaint": 2, "311:Animal in a Park": 2,
                 "311:Mobile Food Vendor": 2, "311:Drinking": 2, "311:Noise - House of Worship": 2}
PER1K_NOUN = {"311:Noise - Helicopter": "helicopter-noise complaints", "311:Noise - Park": "park-noise complaints",
              "311:Noise - House of Worship": "house-of-worship noise complaints", "311:Animal in a Park": "animal-in-a-park reports",
              "311:Mobile Food Vendor": "mobile-food-vendor complaints", "311:Cannabis Retailer": "cannabis-retailer complaints",
              "311:Dead/Dying Tree": "dead-or-dying-tree reports", "311:Lost Property": "lost-property reports",
              "rat_signs": "failed rodent inspections"}


LICENSE_WEIGHTS = {"Pawnbroker": 2, "Tow Truck Company": 2, "Car Wash": 2, "Scrap Metal Processor": 2,
                   "Garage & Parking Lot": 1, "Self-Storage Facility": 2, "Newsstand": 1.5}


def registry():
    """-> list of dict(key, kind in {count, per1k, density}, noun, weight)"""
    reg = []
    for key in metrics:
        if key in COUNT_NOUNS:
            reg.append(dict(key=key, kind="count", noun=COUNT_NOUNS[key][0], weight=COUNT_NOUNS[key][1]))
        elif key.startswith("311:") or key == "rat_signs":
            noun = PER1K_NOUN.get(key, key.split(":", 1)[-1].lower() + " complaints")
            reg.append(dict(key=key, kind="per1k", noun=noun, weight=PER1K_WEIGHTS.get(key, 1)))
        elif key.startswith("species:"):
            reg.append(dict(key=key, kind="count", noun=f"{key[8:]} street trees", weight=0.5))
        elif key.startswith("cuisine:") and "Bagels" not in key:
            reg.append(dict(key=key, kind="count", noun=f"{key[8:]} restaurants", weight=3))
        elif key.startswith("license:"):
            reg.append(dict(key=key, kind="count", noun=f"active {key[8:].lower()} licenses", weight=LICENSE_WEIGHTS.get(key[8:], 0.5)))
    return reg


def values(m):
    """{nta: normalized value} over RES for a registry entry."""
    src = metrics[m["key"]]
    if m["kind"] == "count":
        return {i: float(src.get(i, 0)) for i in IDS}
    if m["kind"] == "per1k":   # only neighborhoods with enough residents and raw volume
        return {i: 1000 * src.get(i, 0) / POP[i] for i in IDS if POP[i] >= MIN_POP_PER_CAPITA and src.get(i, 0) >= 30}
    return {i: src.get(i, 0) / AREA[i] for i in IDS}


def top_set(vals, k):
    """Neighborhoods tied for the top k by value (all with value >= the k-th value); None if ambiguous."""
    order = sorted(vals.values(), reverse=True)
    if len(order) < k or order[k - 1] <= 0:
        return None
    s = [i for i, v in vals.items() if v >= order[k - 1]]
    return s if len(s) <= k + 2 else None


def bottom_quartile(vals):
    order = sorted(vals.values())
    q = order[len(order) // 4]
    return {i for i, v in vals.items() if v <= q}


# ---------------------------------------------------------------- clue builders
def add(out, nta, tier, template, text, matches, quality):
    out[nta].append({"template": template, "tier": tier, "text": text, "matches": sorted(matches), "quality": quality})


def top_clues(out, reg):
    for m in reg:
        vals = values(m)
        for k, tier in ((TOP_TIGHT, 1), (TOP_BROAD, 2)):
            s = top_set(vals, k)
            if not s:
                continue
            per = " per resident" if m["kind"] == "per1k" else ""
            for i in s:
                if tier == 1 and m["kind"] == "count" and vals[i] < 3:
                    continue
                add(out, i, tier, f"top{k}:{m['key']}",
                    f"It is one of the {k} neighborhoods in NYC with the most {m['noun']}{per}.", s, m["weight"] + (1 if tier == 1 else 0))


def compound_clues(out, reg):
    """Bottom-quartile compounds across commercial-activity metrics: 'quiet, residential' clues."""
    fam = [m for m in reg if m["key"] in ("restaurants", "count:hotels", "count:cultural_orgs", "count:wifi_hotspots",
                                         "count:parking_meters", "count:bike_parking", "count:public_art", "count:bus_shelters")
           or m["key"] in ("311:Noise - Park", "311:Noise - House of Worship", "311:Outdoor Dining", "311:Mobile Food Vendor",
                           "311:Cannabis Retailer", "311:Panhandling", "311:Drinking")
           or m["key"] in ("license:Electronics Store", "license:Tobacco Retail Dealer", "license:Garage & Parking Lot")]
    for m in fam:
        if m["key"] == "restaurants":
            m.update(kind="count", noun="restaurants")
    bq = {}
    for m in fam:
        v = values(m) if m["key"] != "restaurants" else {i: float(metrics["restaurants"].get(i, 0)) for i in IDS}
        bq[m["key"]] = (bottom_quartile(v), m)
    for i in IDS:
        cands = sorted((k for k, (s, _) in bq.items() if i in s), key=lambda k: len(bq[k][0]))[:14]
        best = []
        for combo in itertools.combinations(cands, 3):
            inter = set.intersection(*(bq[k][0] for k in combo))
            best.append((len(inter), combo, inter))
        best.sort(key=lambda t: t[0])
        seen = set()
        for size, combo, inter in best[:3]:
            if size > 14 or combo in seen:
                continue
            seen.add(combo)
            nouns = [bq[k][1]["noun"] for k in combo]
            text = f"It is in the bottom quartile of NYC neighborhoods for {nouns[0]}, {nouns[1]} and {nouns[2]}."
            add(out, i, 1, "bottomq:" + "+".join(sorted(combo)), text, inter, 3.5)


def density_clues(out, reg):
    dens = [("restaurants", "restaurants"), ("street_trees", "street trees"), ("landmarks", "landmarked buildings"),
            ("subway_stations", "subway stations")]
    for key, noun in dens:
        d = {i: metrics.get(key, {}).get(i, 0) / AREA[i] for i in IDS}
        order = sorted(IDS, key=lambda i: (-d[i], i))
        rank = {i: r + 1 for r, i in enumerate(order)}
        for i in IDS:
            if metrics.get(key, {}).get(i, 0) < 5:
                continue
            r = rank[i]
            for pct in (10, 20):
                cut = int(pct * N / 100)
                if r <= cut:
                    top = set(order[:cut])
                    add(out, i, 2, f"densetop{pct}:{key}",
                        f"Per square kilometre, it is in the top {pct}% of NYC neighborhoods for {noun}.", top, 1.5)
                    break
            else:
                cut = int(20 * N / 100)
                if r > N - cut and d[i] > 0:
                    bot = set(order[-cut:])
                    add(out, i, 2, f"densebot20:{key}",
                        f"Per square kilometre, it is in the bottom 20% of NYC neighborhoods for {noun}.", bot, 1)


DEMO = [  # key, value scale, step, high text, low text
    ("median_income_k", 1000, 10, "Median household income is over ${t:,.0f}.", "Median household income is under ${t:,.0f}."),
    ("median_age", 1, 2, "The median age is over {t:.0f}.", "The median age is under {t:.0f}."),
    ("pct_under18", 1, 2, "More than {t:.0f}% of residents are under 18.", "Fewer than {t:.0f}% of residents are under 18."),
    ("pct_65plus", 1, 2, "More than {t:.0f}% of residents are 65 or older.", "Fewer than {t:.0f}% of residents are 65 or older."),
    ("pct_renter", 1, 5, "Over {t:.0f}% of households rent.", "Fewer than {t:.0f}% of households rent."),
    ("pct_foreign_born", 1, 5, "Over {t:.0f}% of residents were born outside the US.", "Fewer than {t:.0f}% of residents were born outside the US."),
    ("pct_ba", 1, 5, "Over {t:.0f}% of adults hold a bachelor's degree or higher.", "Fewer than {t:.0f}% of adults hold a bachelor's degree or higher."),
    ("pct_no_car", 1, 5, "Over {t:.0f}% of households have no car.", "Fewer than {t:.0f}% of households have no car."),
    ("pct_transit", 1, 5, "Over {t:.0f}% of commuters take public transit.", "Fewer than {t:.0f}% of commuters take public transit."),
    ("pct_wfh", 1, 5, "Over {t:.0f}% of workers work from home.", "Fewer than {t:.0f}% of workers work from home."),
    ("pct_walk", 1, 5, "Over {t:.0f}% of commuters walk to work.", "Fewer than {t:.0f}% of commuters walk to work."),
]
EXTREME_PCT = 0.15


def demo_clues(out):
    for key, scale, step, hi, lo in DEMO:
        vals = {i: demo[i][key] for i in IDS if demo[i].get(key) is not None}
        order = sorted(vals, key=lambda i: vals[i])
        cut = int(EXTREME_PCT * len(order))
        for i in order[-cut:]:
            t = math.floor(vals[i] / step) * step
            s = {j for j, v in vals.items() if v >= t}
            add(out, i, 3, f"demo_hi:{key}", hi.format(t=t * scale), s, 2)
        for i in order[:cut]:
            t = math.ceil(vals[i] / step) * step
            s = {j for j, v in vals.items() if v <= t}
            add(out, i, 3, f"demo_lo:{key}", lo.format(t=t * scale), s, 2)
    # largest group, when it is a strong plurality
    for i in IDS:
        d = demo[i]
        if d["top_group_pct"] >= 45:
            t = math.floor(d["top_group_pct"] / 5) * 5
            s = {j for j in IDS if demo[j]["top_group"] == d["top_group"] and demo[j]["top_group_pct"] >= t}
            grp = {"White": "non-Hispanic white", "Black": "Black", "Asian": "Asian", "Hispanic": "Hispanic or Latino"}[d["top_group"]]
            add(out, i, 3, f"demo_group:{d['top_group']}", f"The largest racial/ethnic group is {grp}, at over {t}% of residents.", s, 2)


def tier45(out):
    for i in IDS:
        same = [j for j in IDS if BORO[j] == BORO[i]]
        add(out, i, 4, "borough", f"It is in {'the ' if BORO[i] == 'Bronx' else ''}{BORO[i]}.", same, 2)
    routes = {i: tuple(sorted({r for s in st for r in s["routes"]})) for i, st in labels["subway"].items() if i in POP}
    for i, r in routes.items():
        s = [j for j in IDS if routes.get(j) == r]
        add(out, i, 5, "subway_lines", "Subway lines serving it: " + ", ".join(r) + ".", s, 2)
    for i, names in labels["landmark_names"].items():
        if i in POP and names:
            pick = sorted(set(names))[:3]
            add(out, i, 5, "landmark_name", "Landmarks here include: " + "; ".join(pick) + ".", [i], 2)


def main():
    out = {i: [] for i in IDS}
    reg = registry()
    top_clues(out, reg); compound_clues(out, reg); density_clues(out, reg); demo_clues(out); tier45(out)
    for n in RES:   # a clue may not contain a >=4-letter token of its own neighborhood's name
        toks = {t.lower() for t in n["name"].replace("-", " ").replace("/", " ").split() if len(t) >= 4}
        out[n["id"]] = [c for c in out[n["id"]] if c["tier"] == 4 or not any(t in c["text"].lower() for t in toks)]
    (DATA / "clues.json").write_text(json.dumps(out))
    cover = {t: sum(1 for i in IDS if any(c["tier"] == t for c in out[i])) for t in (1, 2, 3, 4, 5)}
    full = sum(1 for i in IDS if all(any(c["tier"] == t for c in out[i]) for t in (1, 2, 3, 4, 5)))
    print(f"{N} residential neighborhoods; tier coverage {cover}; full ladder: {full}")
    t1 = [c for i in IDS for c in out[i] if c["tier"] == 1]
    print("tier-1 clues:", len(t1), "| single top-5:", sum(c["template"].startswith("top5") for c in t1),
          "| compound:", sum(c["template"].startswith("bottomq") for c in t1))


if __name__ == "__main__":
    main()
