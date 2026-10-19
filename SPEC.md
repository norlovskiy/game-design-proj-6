# NYC Neighborhood Daily: Spec (v1)

A daily puzzle game. Players guess an NYC neighborhood from clues derived from NYC Open Data (https://www.nyc.gov/opendata). Distribution: itch.io (HTML5 upload) only.

## 1. Gameplay

- One puzzle per day, identical for all players.
- Puzzle day boundary: midnight `America/New_York`, computed client-side with `Intl.DateTimeFormat`.
- **Launch date: 2026-10-19** (puzzle #1). Puzzle number = days since launch + 1.
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
