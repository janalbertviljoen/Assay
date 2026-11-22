# VI_202611_003: Personal buy list with price curves in the S&P 500 report

| Field | Value |
|---|---|
| Status | done, 2026-11-22 |
| Priority | high |
| Kind | new capability |
| Depends on | VI_202610_006, VI_202610_007 |
| Branch | `feature/value-investing/vi-202611-003-personal-buy-list` |
| Raised | 2026-11-19 |

## Description

The user wanted to move part of their index funds into individual US companies: the 10
picks of the S&P 500 report plus a fixed position in NVIDIA. Before deciding, the user
wanted to see each pick's price over time, whether it sits in a dip, and the buy list
under several weightings, to judge by eye. The strategy itself does not change.

## Outcome

Done on 2026-11-22. The S&P 500 report shows a buy list and the price trends of the next
picks and of the investor's own purchases; a short `buy` report gives only that. The
model, the picks and the backtest are unchanged: the wallets still weight by score.

- **Buy list** (`value_investing.buy_list`): the picks' money under four weightings side
  by side, by score (the model's weights), by rank (equal steps from 3 to 1), by dip (the
  same steps, the price lowest in its five-year range first) and a blend of two parts
  rank to one part dip; the investor's fixed purchases (NVIDIA) the same under all four
  and never in the wallets. Amounts in the investor's currency, turned into USD at the
  latest FRED DEXSFUS rate on or before the report date, buying fractional shares. The
  table shows amounts only.
- **Price trends** (`skatkis.financial_logic.price_trend`): five years of price against
  the 200-day mean, shaded more than 20% below the 52-week high, beside the slope of the
  50-day exponential mean of the log price, on `close` (split-adjusted, dividends
  excluded); a table of the place in the five-year range and the state read from them
  (falling, falling but slowing, turning up below trend, rising above trend).
- **Commands**: `buyability --no-plots` scores without the diagnostic plots; `buy` writes
  only `buy_report.pdf` (picks, price history, buy list, trends). Reports keep only the
  PDF and focus on the picks (user, 2026-11-19).
- **Privacy** (user, 2026-11-22, after the Warden): the investor's amounts (currency,
  picks amount, fixed purchases) live in the private input of the steward
  (S_202611_006); `config/rules.toml` keeps a neutral default (USD, no fixed purchase)
  and every analysis setting. The buy list appears only in reports of indices with
  `buy_list = true` (the S&P 500).
- **Structure**: the buying steps moved out of `__main__` into `value_investing.buying`
  (IO-free) and the stored-table reads into `value_investing.io`; the exchange rate is
  checked through its own `REPORT_TABLES`, so `INPUT_TABLES` stays what the pipeline
  reads. The full report of 2026-11-19 rebuilt after the refactor was byte-identical in
  every table except the buy list's new columns.
- **Alternatives considered**: the one-year high as the dip measure (rejected: a stock
  flat at its low for a year read as near its high); a two-year range (the five-year
  range kept: it sees a stock still well below its earlier price while recovering);
  whole shares (dropped for fractional); a dip rule in the model's score (deferred, to
  be backtested as its own methodology change, see notes); the blend as the wallets'
  weighting (VI_202611_004, not adopted).
- **Reviews**: no Inspector runs; the Warden on 2026-11-22 at commit fffc8d6 (two
  blocking findings, the private report text and a tracked local settings file, both
  fixed; the two unpushed commits were rebuilt without them as 96dff7e). The Scribe wrote
  the docstrings and the specification's §5.1; the Tester wrote the unit tests.
