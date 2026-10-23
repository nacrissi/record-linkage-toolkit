# record-linkage-toolkit

[![tests](https://github.com/nacrissi/record-linkage-toolkit/actions/workflows/test.yml/badge.svg)](https://github.com/nacrissi/record-linkage-toolkit/actions/workflows/test.yml)

**Two lists of the same stores that never agree. Five matching passes resolve most rows, a person decides the rest, and their decisions are matched automatically from then on.**

Every field team has this problem. There's a clean master list of stores, with ids, chains and addresses. Then there's what reps actually type into a weekly report: `CORNERSTONE MOBILE PLA  ZA`, `Rio Fresh Mkt #29`, `PRAIRIE SUPPL CO No 24`. Before any number can go in a deck, someone has to work out which store each row means. By hand, that's a weekly afternoon of squinting and VLOOKUPs, and the same mismatches come back the next week.

This toolkit matches what it can prove, refuses to guess when two stores look alike, and turns every human decision into a rule for next time.

All data here is invented and generated from a seed: 400 stores across 8 fictional chains, and 600 field-report rows with realistic typing noise.

## Before and after

| | By hand | With the toolkit |
|---|---|---|
| Matching 600 report rows | Row by row, every week | 527 matched automatically on the first run |
| A row that could be two stores | Someone picks one | Sent to triage with the top 3 candidates and their scores |
| A store that isn't on the list | Gets forced onto the closest name | Stays unmatched and goes to triage |
| Last week's fixes | Redone from memory | Learned as aliases and matched first, next run |
| "How sure are we?" | Unknown | Every match carries its pass, score and confidence band |

## What a run looks like

`make demo` runs the matcher, applies a set of human triage decisions, and runs it again.

**Run 1, no learned aliases:** 527 of 600 rows matched (87.8%), 73 to triage.

**Run 2, after learning 45 decisions:**

| Pass | Description | Rows matched | Cumulative matched | Cumulative % |
|---|---|---|---|---|
| 0 | Learned aliases (pass 0) | 45 | 45 | 7.5% |
| 1 | Exact match on normalized key | 173 | 218 | 36.3% |
| 2 | Normalized + abbreviation expansion | 90 | 308 | 51.3% |
| 3 | Store-number token cross-check | 126 | 434 | 72.3% |
| 4 | Token-set similarity, blocked by city | 78 | 512 | 85.3% |
| 5 | Jaro-Winkler fuzzy match | 60 | 572 | 95.3% |

28 rows (4.7%) went to triage. Checked against the generator's answer key:

```
Overall auto-match precision: 567/572 = 99.13%
Overall recall (of rows with a true match): 550/571 = 96.32%
```

Triage looks like this. A person fills in `decision`, and the next run learns it:

```
report_row_id,store_text,city,candidate_1_store_id,candidate_1_score,candidate_2_store_id,candidate_2_score,...,decision
FR0383,CORNERSTONE MOBILE PLA  ZA,Cedar Falls,ST0075,0.992,ST0283,0.9564,...,
```

Full output: [`docs/sample-output/`](docs/sample-output/).

## How it works

Each row goes through the passes in order and stops at the first one that matches. Cheap, certain passes go first. Fuzzy passes come last and carry the strictest rules.

0. **Learned aliases.** Exact lookup of text a person already resolved, keyed by text and city.
1. **Exact.** Same name and city after lowercasing and stripping accents, punctuation and extra spaces.
2. **Normalized.** `St`/`Ctr`/`Blvd` expanded and the chain prefix dropped, so `Rio Fresh Mkt #29` meets `Rio Fresh Market #29`.
3. **Store number.** Pulls `#24`, `No 24` or `Number 24` from the text and checks the chain and city agree, so `PRAIRIE SUPPL CO No 24` finds `Prairie Supply Co #24`.
4. **Token set.** Word overlap, only against stores in the same city.
5. **Fuzzy.** Jaro-Winkler similarity. It must clear a threshold *and* beat the runner-up by a margin. If two stores are too close to call, the row goes to triage.

```
linkage/
  normalize.py      text cleanup and abbreviation expansion
  jaro_winkler.py   string similarity, written from scratch
  passes.py         the five passes, one small function each
  matcher.py        runs the passes, writes matches, triage and the report
  learn.py          turns triage decisions into aliases
  evaluate.py       precision and recall against the answer key
  generate.py       seeded fake data
```

## Design decisions

- **Refuse before guessing.** Pass 5 needs a clear winner, not just a high score. A wrong match is worse than an unmatched row, because a wrong match looks finished and nobody checks it.
- **Learned aliases are the most trusted pass, so they're guarded.** The learner refuses any decision whose text and city could point to more than one store, and reports it. On the demo data, pass 0 is 45 for 45.
- **Thresholds were tuned on a different seed.** The pass 4 and pass 5 settings came from a separate dataset (seed 11). The numbers above are from seed 7, which the tuning never saw. Tuning and reporting on the same data would flatter the result.
- **The answer key never touches the matcher.** `truth.csv` exists only for `evaluate` and the tests.
- **Every match shows its work.** Each row records which pass matched it and its score, so a reviewer can sort by confidence and spot-check the weakest matches first.
- **Standard library only.** Jaro-Winkler is implemented here and tested against the published reference values. `pytest` is the only dev dependency.

**What's left in triage, and why.** Of the 73 rows in run 1's triage, 28 have no real store on the list. They belong in triage. Most of the rest are compound noise, such as a bare `#42` with no chain name, in a city where two different chains each have a store #42. A person can resolve those in seconds, and the toolkit shouldn't guess at them.

## Run it in 2 minutes

Needs Python 3.10 or newer. No runtime dependencies.

```bash
git clone https://github.com/nacrissi/record-linkage-toolkit.git
cd record-linkage-toolkit
python3 -m pip install -r requirements-dev.txt   # pytest only
make test    # 37 tests
make demo    # match, learn, match again, evaluate
```

On your own lists:

```bash
python3 -m linkage match --master your_master.csv --field-report your_report.csv --aliases aliases.csv --out out
# fill in the decision column in out/triage.csv, then:
python3 -m linkage learn --triage out/triage.csv --aliases aliases.csv --master your_master.csv
```

## The real story

This is a from-scratch rebuild of one piece of my work on a retail field-sales program. No employer code or data is in this repo.

For a 172-store retail pilot in Mexico, I built the executive-reporting pipeline from zero in one week: a weekly ingest, a 5-pass fuzzy/typo name matcher that resolves cross-source mismatches, retail-chain attribution, a self-healing roster, a triage UI for unmapped records, and an auto-generated leadership deck. It cut manual slide maintenance about 90%.

## License

MIT
