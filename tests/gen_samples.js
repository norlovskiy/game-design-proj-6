// Usage: node gen_samples.js <payload.json> <count>. Prints generator output for fixed seeds, as JSON.
const fs = require("fs");
const Endless = require("../web/endless.js");
const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const count = +process.argv[3];
const gen = Endless.create(payload);
const puzzles = [];
for (let i = 0; i < count; i++) {
  const seed = "T" + String(i).padStart(5, "0").replace(/[01]/g, "2");
  const a = gen.generate(seed), b = gen.generate(seed);
  puzzles.push({ seed, hood: a.hood, defs: a.defs, deterministic: JSON.stringify(a) === JSON.stringify(b) });
}
// exhaustive viability, independent of generate(): can the unordered search find any combo?
const viable = gen.viable.filter(h => gen.search(h, l => l));
const codes = ["1-ABC234", "xx 1-k7qm2x yy", "1-ABC23", "1-ABC230", "NYClue Endless 1-K7QM2X 3/5"].map(t => Endless.parseCode(t));
console.log(JSON.stringify({ puzzles, viable, all: gen.viable, codes }));
