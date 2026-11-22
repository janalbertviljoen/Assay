# VI_202611_004: Blended rank and dip weighting of the wallet's purchases

| Field | Value |
|---|---|
| Status | done (not adopted), 2026-11-19 |
| Priority | high |
| Kind | methodology |
| Depends on | VI_202611_003 (the dip measure and the rank ramp) |
| Branch | — |
| Raised | 2026-11-19 |

## Description

The wallet weights each decision's picks by score (weight = score / sum of the picks'
scores), which spreads the money almost evenly. The buy list of VI_202611_003 showed two
other weightings, by rank (equal steps from 3 to 1) and by dip (the same steps, the price
lowest in its five-year range first). The user proposed a blend, two thirds rank and one
third dip, as a new strategy for the wallet's purchases: the dip would change the weights,
never the picks.

## Outcome

Not adopted: the wallet keeps the score weighting (user, 2026-11-19), after a quick
comparison showed no clear difference between score and dip weighting.

- **The comparison** (2026-11-19, data of that date, a scratchpad script; no change to
  the code): the report's wallet with the positions' weights replaced by the dip
  weighting, the place in the five-year range on each decision date taken from prices up
  to that date. Same picks, dates and money (100 USD each January and July, never sold).
  The dip spread the money 5% to 15% of each purchase, the score 8.6% to 12%.

  | Start | Score: value (a year) | Dip: value (a year) | S&P 500 TR |
  |---|---|---|---|
  | 2016 | 8,462 (22.6%) | 8,267 (22.2%) | 5,102 (14.3%) |
  | 2020 | 3,483 (25.1%) | 3,356 (24.0%) | 2,350 (14.2%) |
  | 2023 | 1,411 (28.1%) | 1,411 (28.1%) | 1,103 (15.5%) |
  | 2025 | 487 (18.5%) | 487 (18.5%) | 445 (9.7%) |

  Money-weighted yearly excess of the lots over the S&P 500 TR: before 2022 (fitted)
  score +3.7%, dip +3.1%; from 2022 (held out) score +7.7%, dip +8.1%, with the same
  growth (+97%, +96%). The differences sit within the noise of about 100 lots: the
  picks do the work, and moving money between them changes little.
- **Alternatives not pursued**: the blend itself (two thirds rank, one third dip) and
  the review of Buffett's letters, which would have come before any change to the
  wallet; with score preferred, neither was needed.
- **What remains**: the buy list (VI_202611_003) still shows the rank, dip and blend
  columns beside the score, for the investor's own purchases; the blend's parts are
  `[report.buy_list] blend` in `config/rules.toml`.
