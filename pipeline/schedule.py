"""Build data/schedule.json: one puzzle per day from LAUNCH, shuffled with a fixed seed.

usage: python schedule.py [days]   (default 30)
"""
import datetime as dt
import json
import random
import sys
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
LAUNCH = dt.date(2026, 10, 19)
SEED = 20261019
RECENT = 3  # don't reuse a clue template within this many days

ntas = {n["id"]: n for n in json.loads((DATA / "ntas.json").read_text())}
clues = json.loads((DATA / "clues.json").read_text())

text_count = Counter(c["text"] for cs in clues.values() for c in cs)


def pick(nta, tier, recent):
    cands = [c for c in clues[nta] if c["tier"] == tier]
    fresh = [c for c in cands if c["template"] not in recent]
    return (fresh or cands or [None])[0]


def main(days=30):
    pool = sorted(i for i, cs in clues.items() if all(any(c["tier"] == t for c in cs) for t in (1, 2, 3, 5)))
    random.Random(SEED).shuffle(pool)
    if days > len(pool):
        sys.exit(f"only {len(pool)} eligible neighborhoods; cannot schedule {days} days without repeats")
    sched, recent = [], []
    for d in range(days):
        nta = pool[d]
        used = {t for r in recent[-RECENT:] for t in r}
        c1, c2, c3, c5 = (pick(nta, t, used) for t in (1, 2, 3, 5))
        recent.append({c["template"] for c in (c1, c2, c3, c5)})
        sched.append({
            "day": d + 1,
            "date": (LAUNCH + dt.timedelta(days=d)).isoformat(),
            "answer": nta,
            "answer_name": ntas[nta]["name"],
            "clues": [c1["text"], c2["text"], c3["text"], f"It is in {ntas[nta]['borough']}.", c5["text"]],
            "templates": [c1["template"], c2["template"], c3["template"], "borough", c5["template"]],
            "clue1_matches": text_count[c1["text"]],
        })
    (DATA / "schedule.json").write_text(json.dumps(sched, indent=1))
    print(f"eligible pool: {len(pool)}; wrote {days} days from {sched[0]['date']}")
    for s in sched[:4]:
        print(f"\n#{s['day']} {s['date']} -> {s['answer_name']} (clue1 shared by {s['clue1_matches']} NTAs)")
        for k, t in enumerate(s["clues"], 1):
            print(f"  {k}. {t}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 30)
