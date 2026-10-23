# Match Report

| Pass | Description | Rows matched | Cumulative matched | Cumulative % |
|---|---|---|---|---|
| 0 | Learned aliases (pass 0) | 45 | 45 | 7.5% |
| 1 | Exact match on normalized key | 173 | 218 | 36.3% |
| 2 | Normalized + abbreviation expansion | 90 | 308 | 51.3% |
| 3 | Store-number token cross-check | 126 | 434 | 72.3% |
| 4 | Token-set similarity, blocked by city | 78 | 512 | 85.3% |
| 5 | Jaro-Winkler fuzzy match | 60 | 572 | 95.3% |

28 rows (4.7% of 600) went to triage: unmatched or too ambiguous to auto-match.
