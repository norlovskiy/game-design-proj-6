// Endless-mode puzzle generator. Inlined into index.html by build.py; also loadable from node (tests/test_endless.py).
// Rules come from data/rules.json (shared with pipeline/solver.py) and arrive inside the payload.
const Endless = (() => {
  const ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ";   // no 0/O, 1/I
  const CODE_LEN = 6;

  function hashSeed(str) {   // FNV-1a
    let h = 2166136261;
    for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }
  function rng(seed) {   // mulberry32
    let a = hashSeed(seed);
    return () => {
      a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function metricKeys(template) {   // mirrors solver.metric_keys
    const i = template.indexOf(":"), head = i < 0 ? template : template.slice(0, i), rest = i < 0 ? "" : template.slice(i + 1);
    if (head === "bottomq") return rest.split("+");
    return [rest || head];
  }

  // payload: {v, rules, ids, defs: [[tier, text, template, [matchIdx], photo]], hoods: {id: [[defIdx, quality]]}}
  function create(payload) {
    const { rules, ids, defs, hoods } = payload;
    const limits = Object.fromEntries(Object.entries(rules.limits).map(([k, v]) => [+k, v]));
    const famLimited = new Set(rules.family_limited);
    const match = defs.map(d => new Set(d[3]));
    const keys = defs.map(d => metricKeys(d[2]));
    const fams = keys.map(ks => ks.map(k => k.split(":")[0]).filter(f => famLimited.has(f)));
    const byTier = {};   // hood -> tier -> [[defIdx, quality]]
    for (const [h, list] of Object.entries(hoods)) {
      byTier[h] = { 1: [], 2: [], 3: [], 4: [], 5: [] };
      for (const e of list) byTier[h][defs[e[0]][0]].push(e);
    }
    const viable = Object.keys(hoods).sort();

    // mirrors solver.acceptable on the profile of a full 5-clue combo
    function acceptable(sizes) {
      for (const k in limits) if (sizes[k - 1] > limits[k]) return false;
      return sizes[0] > sizes[1] && sizes[1] >= sizes[2] && sizes[2] >= sizes[3] &&
        sizes[0] >= rules.min_after_clue1 && sizes[1] >= rules.min_after_clue2;
    }
    const intersect = (a, b) => { const o = new Set(); for (const x of a) if (b.has(x)) o.add(x); return o; };

    // Visits combos for one neighborhood depth-first; `order(list)` fixes the visiting order of each tier's candidates.
    // Returns the first acceptable combo (array of defIdx), or null.
    function search(hood, order) {
      const tiers = byTier[hood], chosen = [], sizes = [];
      function rec(t, cur, usedKeys, usedFams) {
        if (t > 5) return acceptable(sizes) ? chosen.slice() : null;
        for (const [d] of order(tiers[t])) {
          if (keys[d].some(k => usedKeys.has(k)) || keys[d].length !== new Set(keys[d]).size) continue;
          if (fams[d].some(f => usedFams.has(f)) || fams[d].length !== new Set(fams[d]).size) continue;
          const next = t === 1 ? match[d] : intersect(cur, match[d]);
          if (t === 2 && !(sizes[0] > next.size)) continue;
          if (limits[t] !== undefined && next.size > limits[t]) continue;
          chosen.push(d); sizes.push(next.size);
          const r = rec(t + 1, next, new Set([...usedKeys, ...keys[d]]), new Set([...usedFams, ...fams[d]]));
          if (r) return r;
          chosen.pop(); sizes.pop();
        }
        return null;
      }
      return rec(1, null, new Set(), new Set());
    }

    // weighted order without replacement (weight = quality^2): Efraimidis-Spirakis keys
    const weighted = rand => list =>
      list.map(e => [Math.pow(rand(), 1 / (e[1] * e[1])), e]).sort((a, b) => b[0] - a[0]).map(x => x[1]);

    function generate(seed) {
      const rand = rng(seed);
      const hood = viable[Math.floor(rand() * viable.length)];
      const combo = search(hood, weighted(rand));
      return { seed, hood, defs: combo, clues: combo.map(d => defs[d][1]), photos: combo.map(d => defs[d][4] || null) };
    }
    return { viable, generate, search, defs, rules };
  }

  function randomSeed() {
    let s = "";
    for (let i = 0; i < CODE_LEN; i++) s += ALPHABET[Math.floor(Math.random() * ALPHABET.length)];
    return s;
  }
  const formatCode = (version, seed) => `${version}-${seed}`;
  // Accepts a bare code or a whole share text; returns {version, seed} or null.
  function parseCode(text) {
    const m = new RegExp(`(?:^|[^0-9A-Za-z])(\\d+)-([${ALPHABET}]{${CODE_LEN}})(?![0-9A-Za-z])`, "i").exec(String(text).toUpperCase());
    return m ? { version: +m[1], seed: m[2] } : null;
  }

  return { create, randomSeed, formatCode, parseCode, ALPHABET };
})();
if (typeof module !== "undefined") module.exports = Endless;
