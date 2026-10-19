"""Pull each dataset, aggregate per 2020 NTA, write data/metrics.json.

Output shape: {metric_key: {nta_id: value}} for numeric metrics, and
{"_labels": {...}} for categorical lookups (e.g. top tree species per NTA).
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

from assign import NTAS, assign, fetch_all
from socrata import query

OUT = Path(__file__).resolve().parent.parent / "data" / "metrics.json"
SINCE = "2025-01-01T00:00:00"

# 311 complaint types worth building clues from (mid-volume and recognisable).
COMPLAINTS_311 = [
    "Rodent", "Noise - Helicopter", "Illegal Fireworks", "Graffiti", "Dead Animal",
    "Panhandling", "Taxi Complaint", "Noise - Park", "Animal in a Park", "Drinking",
    "Urinating in Public", "Unleashed Dog", "Unsanitary Pigeon Condition",
    "Dead/Dying Tree", "Lost Property", "Mobile Food Vendor", "Outdoor Dining",
    "Cannabis Retailer", "Abandoned Bike", "Noise - House of Worship",
]


CUISINES = ("Ethiopian", "Afghan", "Russian", "Polish", "Filipino", "Bangladeshi", "Pakistani", "Brazilian",
            "German", "Egyptian", "Armenian", "Hawaiian", "Caribbean", "Korean", "Thai", "Bagels/Pretzels")


def pts(rows, lat="lat", lon="lon"):
    ok = [r for r in rows if r.get(lat) and r.get(lon)]
    return ok, assign([float(r[lat]) for r in ok], [float(r[lon]) for r in ok])


def count_by_nta(rows, lat="lat", lon="lon", n="n"):
    ok, ids = pts(rows, lat, lon)
    c = Counter()
    for r, i in zip(ok, ids):
        if i:
            c[i] += int(r[n])
    return dict(c)


def hydrants():
    rows = fetch_all("5bgh-vtsn", select="round(latitude,4) as lat, round(longitude,4) as lon, count(*) as n",
                     group="lat, lon", order="lat, lon")
    return {"hydrants": count_by_nta(rows)}


def trees():
    rows = fetch_all("uvpi-gqnh", select="round(latitude,4) as lat, round(longitude,4) as lon, spc_common, count(*) as n",
                     where="status='Alive' AND spc_common IS NOT NULL", group="lat, lon, spc_common",
                     order="lat, lon, spc_common")
    ok, ids = pts(rows)
    total, species = Counter(), defaultdict(Counter)
    for r, i in zip(ok, ids):
        if i:
            total[i] += int(r["n"])
            species[i][r["spc_common"]] += int(r["n"])
    # share of each species city-wide, to find a neighborhood's signature species
    city = Counter()
    for c in species.values():
        city.update(c)
    sig = {}
    for i, c in species.items():
        # species with the highest over-representation vs. city share (min 50 trees)
        best = max((s for s, k in c.items() if k >= 50),
                   key=lambda s: (c[s] / total[i]) / (city[s] / sum(city.values())), default=None)
        sig[i] = {"top": c.most_common(1)[0][0], "top_share": c.most_common(1)[0][1] / total[i], "signature": best}
    return {"street_trees": dict(total), "_labels": {"tree_species": sig}}


def complaints_311():
    out = {}
    for t in COMPLAINTS_311:
        rows = fetch_all("erm2-nwe9", select="round(latitude,3) as lat, round(longitude,3) as lon, count(*) as n",
                         where=f"created_date >= '{SINCE}' AND complaint_type='{t}' AND latitude IS NOT NULL",
                         group="lat, lon", order="lat, lon")
        out[f"311:{t}"] = count_by_nta(rows)
    return out


def restaurants():
    rows = fetch_all("43nn-pn8j", select="round(latitude,4) as lat, round(longitude,4) as lon, cuisine_description, count(distinct camis) as n",
                     where="latitude IS NOT NULL AND latitude != '0'", group="lat, lon, cuisine_description",
                     order="lat, lon, cuisine_description")
    ok, ids = pts(rows)
    total, cuisines = Counter(), defaultdict(Counter)
    for r, i in zip(ok, ids):
        if i and r.get("cuisine_description"):
            total[i] += int(r["n"])
            cuisines[i][r["cuisine_description"]] += int(r["n"])
    return {"restaurants": dict(total),
            **{f"cuisine:{c}": {i: cuisines[i][c] for i in cuisines if cuisines[i][c]}
               for c in CUISINES}}


def rodents():
    rows = fetch_all("p937-wjvj", select="round(latitude,3) as lat, round(longitude,3) as lon, count(*) as n",
                     where="result like 'Failed for Rat Activity%' AND latitude IS NOT NULL", group="lat, lon", order="lat, lon")
    return {"rat_signs": count_by_nta(rows)}


def landmarks():
    rows = fetch_all("buis-pvji", select="latitude, longitude, lpc_name, 1 as n", order="objectid")
    ok, ids = pts(rows, "latitude", "longitude")
    names = defaultdict(list)
    for r, i in zip(ok, ids):
        if i:
            names[i].append(r["lpc_name"])
    return {"landmarks": {i: len(v) for i, v in names.items()}, "_labels": {"landmark_names": names}}


def subway():
    rows = query("5f5g-n3cz", domain="data.ny.gov", limit=2000)
    ids = assign([float(r["latitude"]) for r in rows], [float(r["longitude"]) for r in rows])
    st = defaultdict(list)
    for r, i in zip(rows, ids):
        if i:
            st[i].append({"name": r["stop_name"], "routes": r["daytime_routes"].split()})
    return {"subway_stations": {i: len(v) for i, v in st.items()}, "_labels": {"subway": st}}


def main():
    metrics, labels = {}, {}
    for fn in (hydrants, trees, complaints_311, restaurants, rodents, landmarks, subway):
        print("extracting", fn.__name__, flush=True)
        res = fn()
        labels.update(res.pop("_labels", {}))
        metrics.update(res)
    OUT.write_text(json.dumps({"metrics": metrics, "labels": labels}))
    print("wrote", OUT, "-", len(metrics), "metrics")


if __name__ == "__main__":
    main()
