"""Census ACS 5-year (2020-tract geography) -> per-2020-NTA demographics -> data/demographics.json.

Tracts come from the NYC tract->NTA crosswalk (hm78-6dwm). Counts are summed to NTA; medians
are recomputed from summed bin counts (never averaged across tracts). Cached in data/raw/.
"""
import json
from pathlib import Path

import requests

from socrata import RAW, query

DATA = Path(__file__).resolve().parent.parent / "data"
YEAR = 2023
COUNTIES = ["005", "047", "061", "081", "085"]

INCOME_BINS = [(0, 10), (10, 15), (15, 20), (20, 25), (25, 30), (30, 35), (35, 40), (40, 45), (45, 50),
               (50, 60), (60, 75), (75, 100), (100, 125), (125, 150), (150, 200), (200, 400)]   # $k
INCOME_VARS = [f"B19001_{i:03d}E" for i in range(2, 18)]
# B01001 sex-by-age: male 003-025, female 027-049; 23 identical bins per sex
AGE_BINS = [(0, 5), (5, 10), (10, 15), (15, 18), (18, 20), (20, 21), (21, 22), (22, 25), (25, 30), (30, 35), (35, 40),
            (40, 45), (45, 50), (50, 55), (55, 60), (60, 62), (62, 65), (65, 67), (67, 70), (70, 75), (75, 80),
            (80, 85), (85, 95)]
AGE_M = [f"B01001_{i:03d}E" for i in range(3, 26)]
AGE_F = [f"B01001_{i:03d}E" for i in range(27, 50)]
OTHER = {
    "pop": "B01003_001E",
    "hisp_total": "B03002_001E", "white": "B03002_003E", "black": "B03002_004E", "asian": "B03002_006E", "hispanic": "B03002_012E",
    "foreign_born": "B05002_013E", "nativity_total": "B05002_001E",
    "owner_hh": "B25003_002E", "renter_hh": "B25003_003E",
    "comm_total": "B08301_001E", "comm_transit": "B08301_010E", "comm_walk": "B08301_019E", "comm_bike": "B08301_018E", "comm_wfh": "B08301_021E",
    "edu_total": "B15003_001E", "edu_ba": "B15003_022E", "edu_ma": "B15003_023E", "edu_prof": "B15003_024E", "edu_phd": "B15003_025E",
    "veh_total": "B25044_001E", "veh_none_own": "B25044_003E", "veh_none_rent": "B25044_010E",
}
ALL = INCOME_VARS + AGE_M + AGE_F + list(OTHER.values())


TABLES = ["B19001", "B01001", "B01003", "B03002", "B05002", "B25003", "B08301", "B15003", "B25044"]


def fetch_county(county):
    """Keyless: Census Reporter serves the same ACS 5-year tables as the Census API (which now needs a key)."""
    cache = RAW / f"acs-cr-{county}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    rows, release = {}, {}
    for t in TABLES:     # one table per request: multi-table requests get 403 from the server
        r = requests.get("https://api.censusreporter.org/1.0/data/show/latest",
                         params={"table_ids": t, "geo_ids": f"140|05000US36{county}"}, timeout=300,
                         headers={"User-Agent": "hood-guesser-pipeline"})
        r.raise_for_status()
        j = r.json()
        release = j.get("release", release)
        for geo, tabs in j["data"].items():
            row = rows.setdefault(geo.split("US")[1], {})
            for var, val in tabs[t]["estimate"].items():
                row[f"{var[:-3]}_{var[-3:]}E"] = val
    rows["_release"] = release
    cache.write_text(json.dumps(rows))
    return rows


def median(counts, bins):
    """Linear-interpolated median from bin counts; bins are (lo, hi)."""
    total = sum(counts)
    if total <= 0:
        return None
    half, run = total / 2, 0
    for c, (lo, hi) in zip(counts, bins):
        if run + c >= half and c > 0:
            return lo + (half - run) / c * (hi - lo)
        run += c
    return None


def num(x):
    try:
        v = float(x)
        return v if v >= 0 else 0.0     # Census uses large negatives for suppressed values
    except (TypeError, ValueError):
        return 0.0


def main():
    tracts = {}
    for c in COUNTIES:
        tracts.update(fetch_county(c))
    print("ACS release:", tracts.pop("_release", None))
    xwalk = query("hm78-6dwm", limit=5000)
    agg = {}
    for x in xwalk:
        if x["ntatype"] != "0":
            continue
        t = tracts.get(x["geoid"])
        if not t:
            continue
        a = agg.setdefault(x["ntacode"], {v: 0.0 for v in ALL})
        for v in ALL:
            a[v] += num(t.get(v))
    out = {}
    for nta, a in agg.items():
        g = lambda k: a[OTHER[k]]
        pop = g("pop")
        if pop < 500:
            continue
        ages = [a[m] + a[f] for m, f in zip(AGE_M, AGE_F)]
        groups = {"White": g("white"), "Black": g("black"), "Asian": g("asian"), "Hispanic": g("hispanic")}
        top = max(groups, key=groups.get)
        hh = g("owner_hh") + g("renter_hh")
        out[nta] = {
            "pop": pop,
            "median_income_k": median([a[v] for v in INCOME_VARS], INCOME_BINS),
            "median_age": median(ages, AGE_BINS),
            "pct_under18": 100 * sum(ages[:4]) / sum(ages),
            "pct_65plus": 100 * sum(ages[17:]) / sum(ages),
            "top_group": top, "top_group_pct": 100 * groups[top] / g("hisp_total"),
            "pct_foreign_born": 100 * g("foreign_born") / g("nativity_total"),
            "pct_renter": 100 * g("renter_hh") / hh if hh else None,
            "pct_transit": 100 * g("comm_transit") / g("comm_total") if g("comm_total") else None,
            "pct_walk": 100 * g("comm_walk") / g("comm_total") if g("comm_total") else None,
            "pct_wfh": 100 * g("comm_wfh") / g("comm_total") if g("comm_total") else None,
            "pct_ba": 100 * (g("edu_ba") + g("edu_ma") + g("edu_prof") + g("edu_phd")) / g("edu_total") if g("edu_total") else None,
            "pct_no_car": 100 * (g("veh_none_own") + g("veh_none_rent")) / g("veh_total") if g("veh_total") else None,
        }
    (DATA / "demographics.json").write_text(json.dumps(out, indent=1))
    print(len(out), "neighborhoods; NYC population covered:", round(sum(v["pop"] for v in out.values())))


if __name__ == "__main__":
    main()
