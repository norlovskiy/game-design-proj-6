# NYClue: Spec (v1)

A daily puzzle game. Players guess an NYC neighborhood from clues derived from NYC Open Data (https://www.nyc.gov/opendata). Distribution: itch.io (HTML5 upload) only.

## 1. Gameplay

- One puzzle per day, identical for all players.
- Puzzle day boundary: midnight `America/New_York`, computed client-side with `Intl.DateTimeFormat`.
- **Launch date: 2026-10-14** (puzzle #1; moved from 10-19 so the demo has six past puzzles by 10-20). Puzzle number = days since launch + 1.
- 5 guesses, 5 clues. Clue 1 is shown at start; each wrong guess reveals the next clue.
- Win: correct guess within 5. Lose: 5 wrong guesses; the answer is highlighted and all clues are listed.
- Day ends on win or loss. Result is stored; replaying the same day is blocked.

### Clue ladder (revised 2026-10-19)
1. Tight: "one of the 5 neighborhoods in NYC with the most X", or a compound "bottom quartile for A, B and C".
2. Broader: density bands (top/bottom 20%) or "one of the 20 neighborhoods with the most X".
3. Demographics from ACS as thresholds (income, age, rent share, largest ethnic group, commute, education...).
4. Borough.
5. Clincher: subway lines or landmark names.

Every clue carries the exact set of neighborhoods it is true for. `pipeline/solver.py` enumerates clue combinations and only accepts ones that narrow gradually (see limits there); `schedule.py` draws from those. Demographics come from ACS 5-year (2020 to 2024) via Census Reporter, joined to 2020 NTAs with the DCP tract crosswalk, and the credits screen must name the Census Bureau.

(Original ladder, superseded:)
| # | Content |
|---|---------|
| 1 | Very niche stat |
| 2 | Niche stat |
| 3 | Middling stat |
| 4 | Borough |
| 5 | Clincher: landmark or subway lines in the neighborhood |

### Guessing UI
- Click a neighborhood on an outline-only map (no labels, no streets). Borough tint and water are shown.
- Tapping selects; a "Confirm guess" button submits (prevents mobile misfires). The selected name is shown after selection, before confirm.
- Wrong guesses are coloured on a warm-to-cold gradient by centroid distance to the answer (warm = close, about 30 km or more = coldest) and listed with their distance in km. No direction arrows. The share card uses 🟨 (<3 km), 🟧 (<10 km), 🟥 (farther), 🟩 (correct), ⬛ (unused).
- All neighborhoods are clickable, including ones excluded from the answer pool.

### Share and persistence
- Emoji share card (e.g. guesses used out of 5) with the puzzle number.
- Copy button uses the Clipboard API; on failure, fall back to a visible, selectable text box.
- Progress and streak are stored in `localStorage`, every access wrapped in try/catch with an in-memory fallback.
- v1 includes a streak counter. Not in v1: stats screen, archive, dark mode.

## 2. Geography

- Unit: NTA (Neighborhood Tabulation Area), with cleaned display names and an alias list.
- Polygons: simplified GeoJSON, rendered as SVG (D3 or plain SVG). No Leaflet, no tiles.
- **Answer pool** excludes non-residential NTAs (parks, airports, cemeteries, islands; threshold about 1,000 residents) and any NTA that cannot fill all five clue tiers with valid clues. Excluded NTAs remain on the map.

## 3. Data pipeline (offline, run manually, local script)

1. Pull data from the Socrata API using SoQL aggregation (`GROUP BY`, `count()`) and an app token. Cache raw pulls on disk.
2. Assign records to NTAs by point-in-polygon. Datasets with only ZIP or community district are dropped in v1.
3. Fill fact templates (about 15 to 25 across tiers 1 to 3 and 5) with computed values. Phrase as ranks or normalized values ("top 5% in the city"), not raw counts.
4. For each neighborhood and tier, pick the most distinctive valid template. If any tier has no valid clue, drop the neighborhood from the answer pool.
5. Generate a pre-shuffled schedule (no repeats until the pool is exhausted), covering about a year from the launch date. The schedule is shipped in the bundle, lightly obfuscated.

### Dataset policy
- Excluded: policing, arrests, evictions, and other topics that stigmatize neighborhoods.
- Candidate datasets: street trees, 311 complaint types, film permits, rodent inspections, fire hydrants, dog licenses, restaurant inspections, housing violations, subway entrances/stations, landmarks, population/income.
- Verify each dataset's availability and fields during the pipeline build; this spec doesn't assume any schema.
- Credits screen lists every dataset used by name.

### LLM role (pre-deploy only)
- Assign a niche-to-common tier to each fact template (a human skims the result).
- Review each generated clue for spoilers and ambiguity.
- The LLM does not write clue text or numbers. Clue text comes from templates filled with computed values.

### Fairness checks (per schedule)
- Automated: the clue is true for the answer, doesn't contain the neighborhood name, and isn't duplicated across tiers.
- LLM spoiler/ambiguity review of every clue.
- Solver simulation: for each puzzle, count the neighborhoods consistent with clue 1 and with clues 1 to 3, to flag puzzles that are too easy or impossible.
- Human playtest the first two weeks, then sampled spot-checks.

### Photos
- Tree-species and landmark clues can show a photo under the clue, loaded only once the clue is revealed, with a credit line.
- Public domain / CC0 only, from Wikimedia Commons. `pipeline/images.py candidates` finds candidates (geosearch near the landmark, or species search), `sheets` builds contact sheets, and each pick is reviewed by eye and recorded in `data/photo_picks.json`; `fetch` downloads picks at 960 px into `data/img/`. A clue with no approved photo shows none.
- Photos ship inside the bundle (`img/`), so the page still makes no external requests.

## 4. Delivery (itch.io)

- Zip upload with `index.html` at the root, relative paths only.
- Self-contained: no CDN scripts, web fonts, or live API calls. JS, CSS, GeoJSON and fact JSON are bundled.
- Layout must work at small iframe sizes and on mobile.
- Test on an itch.io draft page, not only locally (iframe restrictions on localStorage and clipboard).
- The credits/About screen names the NYC Open Data source for each dataset.

## 5. Open items

- Game name and visual style are decided at build time.
- Launch is the day after this spec. The pipeline, a first batch of vetted puzzles, and the itch.io test are the critical path. Launching with a short schedule (say 2 to 4 weeks) and extending it later fits the "run manually" pipeline.

## 6. Endless mode

A second mode beside the daily puzzle: unlimited puzzles, same format (5 clues across the same five tiers, 5 guesses, same map UI and distance-gradient feedback). Daily stays the default and is the only mode that touches the daily streak and puzzle number.

### Generation (client-side)
- Puzzles are compiled in the browser from the shipped clue data (`clues.json`, trimmed for the bundle: match sets stored as index lists, unused fields dropped). No precomputed bank.
- Algorithm: pick a neighborhood uniformly from those with at least one valid combo, then choose one clue per tier by randomized depth-first search, weighting each candidate clue by `quality^2` (no hard quality floor). Dead end means backtrack, then reroll the neighborhood. Never loop on a neighborhood with no valid combo; the viable list is computed up front.
- Hard constraints, the same as the daily solver: candidates remaining after clues 3, 4 and 5 are at most 8, 4 and 2; clue 2 must add information; no metric used twice; at most one clue per puzzle from the limited families (species, cuisine, license, 311).
- These rules live in one shipped config read by both `pipeline/solver.py` and the JS generator. A test runs the JS generator against the Python solver on fixed seeds and checks the outputs agree.
- No per-puzzle spoiler or ambiguity review. Endless puzzles are not the vetted daily set.
- Coverage: the build exhausts the solver's search (no per-tier cap) and ships only neighborhoods with an acceptable combo, and only clues used by some acceptable combo: 126 of 197 neighborhoods, about 110 KB. The rest never appear in endless mode (they stay clickable on the map).
- One difficulty. Limits stay parameterized so a selector can be added later.

### Seeds and codes
- Generation is deterministic per seed for a given data version.
- A puzzle code is `<data version>-<seed>`, for example `2-K7QM2X`, using an alphabet without ambiguous characters (no 0/O, 1/I). Only the latest data ships. A code from another version shows "This puzzle is from an older version of the game". A malformed code shows an error. Either way the current puzzle is left untouched.
- Entry: a "Play a code" field behind a link in the Endless view. It accepts a pasted code or a full share text, and the client extracts the code with a regex. No URL parameters (the itch.io iframe breaks them).
- A code puzzle counts toward played/won but not the streak, and may be replayed. It bypasses the "hide today's daily" rule below, but warns if its answer is today's unplayed daily: "This puzzle's answer is also today's daily. Play it anyway?"

- Starting a code puzzle while an endless puzzle has guesses but is unfinished counts the abandoned one as a loss; with no guesses it is discarded.

### Interaction with the daily
- Endless never uses a clue set identical to any daily puzzle's.
- Until today's daily is finished, endless does not pick today's daily neighborhood.
- Repeat avoidance: the client avoids the neighborhoods and clue combos of the last 20 endless puzzles (kept in `localStorage`). This is done by rerolling the seed when a new puzzle is picked. It never changes what a given seed produces.

### UI and flow
- A Daily | Endless toggle always visible in the header.
- After a win or loss, a "Next puzzle" button. "Skip" is available mid-game; it counts as a loss and reveals the answer like a normal loss.
- The code is shown on the end screen next to the share button.
- Record line on the endless end screen, for example "Won 14 of 20 · streak 3 · best 7". No stats screen; the guess distribution is stored for a later one.

### Persistence
- All access follows the existing `localStorage` rules (try/catch, in-memory fallback).
- The in-progress endless puzzle (seed, guesses) resumes on refresh, so refreshing cannot reroll a puzzle.
- The endless record is stored separately from the daily streak: played, won, guess distribution, current streak and best streak. Code puzzles count toward played and won only.

### Sharing
- Emoji card (`NYClue Endless <code> 3/5` then one tile per guess, padded with ⬛) using the daily legend (🟨 <3 km, 🟧 <10 km, 🟥 farther, 🟩 correct, ⬛ unused), with the code and no puzzle number, for example `NYClue Endless 2-K7QM2X 🟨🟧🟩`. Same Clipboard API and selectable-text fallback as daily.

### Credits
- Unchanged: the credits screen already names every dataset.

## 7. Archive (demo)

- A third button, Archive, sits beside the Daily | Endless toggle. It lists every past puzzle (day number lower than today's), newest first, each with its date and status: Not played, In progress, Solved in n/5, or Missed.
- Selecting one plays it exactly like the daily (same clues, 5 guesses, map). The share card reads `NYClue #n 3/5` with no streak line, and the end screen has a "Back to archive" button.
- Archive plays never touch the daily streak. A past day's own daily record (played on the day) and its archive status are the same record; archive-only plays are stored apart in `localStorage`.
- Today's puzzle is not listed; it is played from Daily.

## 8. Naming

The game is called NYClue. Storage keys are `nyclue` and `nyclue_endless` (fresh keys, since moving the launch date renumbered the puzzles); the itch.io zip is `dist/nyclue.zip`.
