"""Fetch 2020 NTAs and write data/ntas.json: id, name, borough, type, geometry (full precision)."""
import json
from pathlib import Path

from socrata import query

OUT = Path(__file__).resolve().parent.parent / "data" / "ntas.json"


def main():
    rows = query("9nt8-h7nd", limit=1000)
    ntas = [
        {
            "id": r["nta2020"],
            "name": r["ntaname"],
            "borough": r["boroname"],
            "type": r["ntatype"],
            "geometry": r["the_geom"],
        }
        for r in rows
    ]
    OUT.write_text(json.dumps(ntas))
    from collections import Counter
    print(len(ntas), "NTAs; by type:", dict(Counter(n["type"] for n in ntas)))
    for n in ntas:
        if n["type"] != "0":
            print(" ", n["type"], n["id"], n["name"])


if __name__ == "__main__":
    main()
