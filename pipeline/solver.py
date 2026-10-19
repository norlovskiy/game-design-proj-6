"""Solver simulator: how fast do a puzzle's clues narrow the candidate neighborhoods?

For a clue combo (one clue per tier 1-5, shown in order) the candidates after clue k are the
residential NTAs consistent with clues 1..k. The profile [c1, c12, c123, c1234, c12345] says how
guessable the puzzle is for someone who knows the facts.

usage: python solver.py          # report over every neighborhood's best combo
"""
import itertools
import json
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
CLUES = json.loads((DATA / "clues.json").read_text())

# Acceptance rules are shared with the browser generator (web/endless.js) through data/rules.json.
RULES = json.loads((DATA / "rules.json").read_text())
PER_TIER = 6          # candidate clues per tier considered when enumerating combos (daily schedule)
# acceptance limits on the profile (candidates remaining after clue k)
LIMITS = {int(k): v for k, v in RULES["limits"].items()}


def metric_keys(template):
    """Underlying metric(s) of a template, so one puzzle never uses a metric twice."""
    head, _, rest = template.partition(":")
    if head == "bottomq":
        return set(rest.split("+"))
    if head in ("borough",):
        return {"borough"}
    return {rest or head}


FAMILY_LIMITED = tuple(RULES["family_limited"])   # at most one clue per puzzle from each of these


def families(template):
    return {k.split(":")[0] for k in metric_keys_full(template) if k.split(":")[0] in FAMILY_LIMITED}


def metric_keys_full(template):
    head, _, rest = template.partition(":")
    if head == "bottomq":
        return set(rest.split("+"))
    return {rest} if rest else {head}


def profile(combo):
    sets = [set(c["matches"]) for c in combo]
    cur, sizes = set(sets[0]), []
    for k, s in enumerate(sets):
        cur = cur & s if k else cur
        sizes.append(len(cur))
    return sizes


def acceptable(sizes):
    ok = all(sizes[k - 1] <= lim for k, lim in LIMITS.items())
    informative = sizes[0] > sizes[1] and sizes[1] >= sizes[2] and sizes[2] >= sizes[3]   # clue 2 must add information
    # not pinned down before clue 3: later clues must still matter
    return ok and informative and sizes[0] >= RULES["min_after_clue1"] and sizes[1] >= RULES["min_after_clue2"]


def combos(nta, per_tier=PER_TIER):
    """All acceptable clue combos for a neighborhood, best first: (quality, sizes, [clue1..clue5])."""
    by_tier = {t: [] for t in range(1, 6)}
    for c in CLUES[nta]:
        by_tier[c["tier"]].append(c)
    if any(not by_tier[t] for t in range(1, 6)):
        return []
    pick = {t: sorted(by_tier[t], key=lambda c: (-c["quality"], len(c["matches"])))[:per_tier] for t in range(1, 6)}
    out = []
    for combo in itertools.product(*(pick[t] for t in range(1, 6))):
        keys = [metric_keys(c["template"]) for c in combo]
        if len(set().union(*keys)) != sum(len(k) for k in keys):     # duplicated metric
            continue
        fams = [f for c in combo for f in families(c["template"])]
        if len(fams) != len(set(fams)):                                # e.g. two tree-species clues
            continue
        sizes = profile(combo)
        if acceptable(sizes):
            out.append((sum(c["quality"] for c in combo), sizes, list(combo)))
    out.sort(key=lambda t: (-t[0], -t[1][2], t[1][4]))   # prefer gradual narrowing at equal quality
    return out


def main():
    best = {n: combos(n) for n in CLUES}
    ok = {n: b for n, b in best.items() if b}
    print(f"{len(ok)}/{len(CLUES)} neighborhoods have an acceptable combo")
    for k, name in enumerate(["clue1", "clues1-2", "clues1-3", "clues1-4", "all 5"]):
        dist = Counter(b[0][1][k] for b in ok.values())
        print(f"  candidates after {name}: " + ", ".join(f"{v}:{c}" for v, c in sorted(dist.items())[:10]))


if __name__ == "__main__":
    main()
