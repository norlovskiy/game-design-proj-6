"""Build data/schedule.json: one puzzle per day from LAUNCH, shuffled with a fixed seed.

Each puzzle's clue set comes from solver.combos(): the highest-quality combination whose clues narrow
the candidates gradually (see solver.py). Templates are not reused within RECENT days.

usage: python schedule.py [days]   (default 30)
"""
import datetime as dt
import json
import random
import sys
from pathlib import Path

from solver import combos, metric_keys

DATA = Path(__file__).resolve().parent.parent / "data"
LAUNCH = dt.date(2026, 10, 19)
SEED = 20261019
RECENT = 5   # don't reuse a clue metric within this many days

ntas = {n["id"]: n for n in json.loads((DATA / "ntas.json").read_text())}


def main(days=30):
    pool = sorted(n for n in json.loads((DATA / "clues.json").read_text()) if combos(n))
    random.Random(SEED).shuffle(pool)
    if days > len(pool):
        sys.exit(f"only {len(pool)} eligible neighborhoods; cannot schedule {days} days without repeats")
    sched, recent = [], []
    for d in range(days):
        nta = pool[d]
        used = set().union(*recent[-RECENT:]) if recent else set()
        options = combos(nta)
        fresh = [o for o in options if not any(metric_keys(c["template"]) & used for c in o[2] if c["tier"] != 4)]
        quality, sizes, combo = (fresh or options)[0]
        recent.append(set().union(*(metric_keys(c["template"]) for c in combo if c["tier"] != 4)))
        sched.append({
            "day": d + 1,
            "date": (LAUNCH + dt.timedelta(days=d)).isoformat(),
            "answer": nta,
            "answer_name": ntas[nta]["name"],
            "clues": [c["text"] for c in combo],
            "templates": [c["template"] for c in combo],
            "candidates_after_clue": sizes,     # solver simulation: neighborhoods still consistent after each clue
        })
    (DATA / "schedule.json").write_text(json.dumps(sched, indent=1))
    print(f"eligible pool: {len(pool)}; wrote {days} days from {sched[0]['date']}")
    for s in sched[:int(sys.argv[2]) if len(sys.argv) > 2 else 7]:
        print(f"\n#{s['day']} {s['date']} -> {s['answer_name']}  candidates after each clue: {s['candidates_after_clue']}")
        for k, t in enumerate(s["clues"], 1):
            print(f"  {k}. {t}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 30)
