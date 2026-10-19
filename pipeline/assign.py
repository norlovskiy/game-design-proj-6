"""Point-in-polygon assignment of (lat, lon) to 2020 NTA ids."""
import json
from pathlib import Path

from shapely import STRtree, points
from shapely.geometry import shape

NTAS = json.loads((Path(__file__).resolve().parent.parent / "data" / "ntas.json").read_text())
_geoms = [shape(n["geometry"]) for n in NTAS]
_tree = STRtree(_geoms)


def assign(lats, lons):
    """Return a list of NTA ids (or None) aligned with the inputs."""
    pts = points(list(lons), list(lats))
    pt_idx, poly_idx = _tree.query(pts, predicate="within")
    out = [None] * len(pts)
    for p, g in zip(pt_idx, poly_idx):
        out[p] = NTAS[g]["id"]
    return out


def fetch_all(dataset_id, page=50000, domain="data.cityofnewyork.us", **params):
    """Page through a grouped SoQL query (requires an $order for stable paging)."""
    from socrata import query
    rows, offset = [], 0
    while True:
        chunk = query(dataset_id, domain=domain, limit=page, offset=offset, **params)
        rows.extend(chunk)
        if len(chunk) < page:
            return rows
        offset += page
