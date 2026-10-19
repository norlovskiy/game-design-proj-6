"""Checks the browser generator (web/endless.js) against the Python solver rules.

Runs the JS generator on fixed seeds (via node) and verifies every puzzle is one the solver would accept, that the
same seed always gives the same puzzle, and that the set of neighborhoods the JS side considers viable equals the solver's.

usage: .venv/bin/python tests/test_endless.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))
import build
import solver

COUNT = 400


def main():
    payload = build.endless_payload(json.loads((ROOT / "data" / "photos.json").read_text()))
    with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
        json.dump(payload, f)
        f.flush()
        out = subprocess.run(["node", str(ROOT / "tests" / "gen_samples.js"), f.name, str(COUNT)],
                             check=True, capture_output=True, text=True).stdout
    res = json.loads(out)

    py_viable = sorted(n for n in solver.CLUES if solver.combos(n, per_tier=10 ** 9))
    assert sorted(res["all"]) == py_viable, "shipped neighborhoods differ from solver's viable set"
    assert sorted(res["viable"]) == py_viable, "JS search finds a different viable set than the solver"

    defs = payload["defs"]
    by_key = {(c["template"], c["text"]): c for cl in solver.CLUES.values() for c in cl}
    hoods_seen = set()
    for p in res["puzzles"]:
        assert p["deterministic"], f"seed {p['seed']} is not deterministic"
        combo = []
        for d in p["defs"]:
            tier, text, template, _, _ = defs[d]
            c = by_key[(template, text)]
            assert c["tier"] == tier
            assert p["hood"] in c["matches"], f"clue not true for the answer: {text}"
            combo.append(c)
        assert [c["tier"] for c in combo] == [1, 2, 3, 4, 5], p
        keys = [solver.metric_keys(c["template"]) for c in combo]
        assert len(set().union(*keys)) == sum(len(k) for k in keys), f"duplicate metric in {p['seed']}"
        fams = [f for c in combo for f in solver.families(c["template"])]
        assert len(fams) == len(set(fams)), f"duplicate family in {p['seed']}"
        sizes = solver.profile(combo)
        assert solver.acceptable(sizes), f"solver rejects {p['seed']}: {sizes}"
        hoods_seen.add(p["hood"])

    codes = res["codes"]
    assert codes[0] == {"version": 1, "seed": "ABC234"}
    assert codes[1] == {"version": 1, "seed": "K7QM2X"}
    assert codes[2] is None and codes[3] is None   # too short; contains 0
    assert codes[4] == {"version": 1, "seed": "K7QM2X"}
    print(f"ok: {len(res['puzzles'])} puzzles valid, {len(py_viable)} viable neighborhoods, {len(hoods_seen)} seen")


if __name__ == "__main__":
    main()
