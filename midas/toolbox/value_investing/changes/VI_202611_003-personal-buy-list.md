# VI_202611_003: Personal buy list with price curves in the S&P 500 report

| Field | Value |
|---|---|
| Status | in progress |
| Priority | high |
| Kind | new capability |
| Depends on | VI_202610_006, VI_202610_007 |
| Branch | `feature/value-investing/vi-202611-003-personal-buy-list` |
| Raised | 2026-11-19 |

## Description

The user wants to move part of their index funds into individual US companies now: the
10 picks of the S&P 500 report plus a fixed position in NVIDIA, 25,000 USD in all. Before
deciding, the user wants to see each pick's price over time and whether it sits in a dip,
and the buy list under two weightings, to judge by eye. The strategy itself does not
change.

## Agreed approach

- **The S&P 500 report only**, on the data as of 2026-11-19, with the model, the picks and
  the backtest unchanged.
- **A buy-list section**: 20,000 USD across the 10 picks under three weightings side by
  side: by score (as the model weights today), by rank in equal steps from 3 to 1 (15% of
  the 20,000 for the first pick down to 5% for the tenth), and by dip (the same steps, the
  price lowest in its five-year range first); and 5,000 USD in NVIDIA, fixed,
  marked as the user's choice outside the model. Dollars and whole shares at the latest
  close for each.
- **Price curves of the 11 companies**: five years of adjusted close on a log scale with
  the 200-day mean and the stretches more than 20% below the 52-week high shaded, beside
  the slope of the smoothed log price (50-day exponential mean, per year) over the last
  two years; a table of the distance from the 52-week high and the 200-day mean, the slope
  now and a month earlier, and the state read from them.
- NVIDIA appears in the buy list and the curves only, never in the backtest or the wallets:
  putting it into past decisions would credit the model with a choice made in hindsight.

## Decisions

- 2026-11-19, user: the 10 picks as computed, plus 5,000 USD in NVIDIA, constant. NVIDIA
  is not added to the wallet analysis unless it was bought before.
- 2026-11-19, user: the dip is not added to the strategy now. A dip rule (six bins: price
  above or below its 200-day mean, times the smoothed slope falling, slowing or rising) is
  an alternative to backtest later, as a separate methodology change.
- 2026-11-19, user: both weightings are shown; the user judges from the curves.
- 2026-11-19, user: a third weighting, by dip, so that the picks whose price sits low
  after a long fall (PODD, BF-B) get more than those near their high (SNA). It gives the
  rank weighting's 3-to-1 steps in the order of each price's place in its five-year range
  (0 at the low, 1 at the high), lowest first. The one-year high was rejected as the
  measure: BF-B has been flat at its low for a year, so it reads as near its high. The
  weighting is the user's judgement, untested, and the report says so.
- 2026-11-19, user: the amounts are in rand (R20,000 for the picks, R5,000 for NVIDIA),
  bought through the investor's USD account, which sells fractional shares. The buy list
  takes its amounts in `currency`, turns them into USD at the latest FRED DEXSFUS rate on
  or before the report date, and gives fractional shares; the whole-share rounding was
  dropped. The `observations` table is checked through its own list, `REPORT_TABLES`, so
  `INPUT_TABLES` stays exactly what the pipeline reads (2026-11-22, after two tests failed).
- 2026-11-19, user: a fourth column, the blend of two parts rank to one part dip, shown
  beside score, rank and dip; not adopted for the wallets (VI_202611_004).
- 2026-11-19, user: the tax-free account is not sold from; the sleeve is funded from the
  regular rand account and moved to the USD account.
- 2026-11-19, user: reports keep only the PDF and focus on the budget and the picks, not
  every analysis. A short buy report (`value_investing buy`) writes only
  `buy_report.pdf`: the next picks, the buy list and the price trends, built in a
  temporary folder; scoring for it runs with `buyability --no-plots`, and the market
  `check` is not run with a report. The full report stays, on request. This run's files
  of 2026-11-19 are kept.
- 2026-11-19, user: the buy-list table shows only the amounts per weighting (with the
  score and the place in the range); the close and the shares were dropped.
- 2026-11-22, user, after the Warden: the buy amounts (`currency`, `picks_amount`,
  `fixed`) move from `config/rules.toml` into the private input
  (`data/private/steward/finances.toml`, `[buy_list]`); `rules.toml` keeps a neutral default
  (USD, no fixed positions) and every analysis setting (S4). The buy list runs only in the
  reports of indices that enable it (S3).
- 2026-11-22, user: the two unpushed commits are rewritten without the private report text
  and without `.claude/settings.local.json`, which is untracked (B1, B2).
- 2026-11-19: the branch is stacked on `feature/skatkis/s-202611-005-pipeline-schema`,
  not cut from `main`: S_202611_005 also changes `value_investing/__main__.py` and is not
  merged yet. Its pull request follows S_202611_005's.

## Notes

- 2026-11-19: market data update for the S&P 500, 400 and 600 as of 2026-11-19 started;
  179 companies had filed a 10-Q or 10-K since 2026-10-31 by the first third of the run.
- 2026-11-19: update finished (EDGAR 555 companies fetched, 574 reused, 2 failed; prices
  1,151 fetched, 2 failed). S&P 500 report built for 2026-11-19 with the buy list (25,000
  ZAR at 16.93 ZAR per USD, the rate of 13 November) and the trend curves. The picks are
  October's: the latest score date is still 2026-09-18, and the new filings enter at the
  December rebalance. NVDA 147.22, 38% below its high, ranked 38th.
- 2026-11-19: first look at the curves, from prices to 2026-10-30, in a scratchpad
  script: PODD below its 200-day mean and turning up; FSLR and ON still falling; FAST,
  SWKS, EW and BF-B near their highs.

## Warden report

2026-11-22, commit fffc8d6 with a dirty working tree (`Toolbox/value_investing/__main__.py`
and `schema.py`); diff 48cd9b7 to the working tree; no Inspector runs. Covers VI_202611_003
and S_202611_006 (VI_202611_004: records only).

### Blocking

- **B1. Tracked private text breaks the steward's privacy rule.** `config/report_steward.toml`
  (`[portfolio] allocation_text`, `[property] text`, `projection_text`, `figure`,
  `[retirement] text`, `caption`) holds the founder's figures and personal circumstances
  (quoted in the Warden's report; the quotes are left out here for privacy), against
  S_202611_006 ("The committed files hold the role, never a figure"). Fix: placeholders fed
  from `finances.toml`, personal circumstances in private text fields or a git-ignored
  override; check the branch history before the PR.
- **B2. `.claude/settings.local.json` is tracked and committed** (+3 lines: a machine path in
  `additionalDirectories`, the sandbox exclusions and allowed domains), though `CLAUDE.md`
  and `.gitignore` say it is ignored. Fix: `git rm --cached` in its own commit (the Guard's
  area).

### Should fix

- **S1.** The private build goes through `tempfile.TemporaryDirectory()` under `$TMPDIR`,
  outside `data/private/`, against the module's own "Must not". Fix: a temporary folder
  under `data/private/steward/reports/<as_of>/`.
- **S2.** The steward imports `buy_report_inputs` from `value_investing.__main__` (a command
  module used as a library), which passes a hardcoded `Path("results")`. Fix: move it and
  its readers to a library module (for example `value_investing/io.py`); drop the path.
- **S3.** The buy list runs in every index's full report, not only the S&P 500's (agreed
  approach: "The S&P 500 report only"); the S&P 400 and 600 reports would show NVDA and the
  amounts, and fail without FRED. Fix: gate it per index or by a flag.
- **S4.** `picks_amount`, `fixed` (NVDA) and `currency` in `config/rules.toml` describe one
  investor's purchase, not the model; they cut across S_202611_006's privacy line.
  Recommendation: read them from the private input, with a neutral default in `rules.toml`.
  The user's decision.
- **S5.** Placeholder keys built from values (`equity_end_10`, `total_65_6`, …): changing a
  rate or the retirement age raises `KeyError`. Fix: key by scenario name and position.
- **S6.** `Finances.as_of` is never used (stale balances go unnoticed); `Account.source`,
  `Property.cost`, `Property.members_loan` are parsed and never read. Fix: show or check the
  finances' date; use or drop the fields.
- **S7.** Records do not match the code: VI_202611_003 status `agreed` (→ in progress), its
  decision says `observations` joins `INPUT_TABLES` (code: `REPORT_TABLES`), the blend is not
  recorded as its decision, description and Done when still say USD, two weightings and
  whole shares; S_202611_006 status `agreed`, Branch "—" (own branch or the reason it rides
  here); both CHANGELOG rows; the containment widening to `~/Documents/Personal`
  (`AGENTS.md`, `CLAUDE.md`, `guard.md`) has no change file and no `midas/midas.md` entry.
- **S8.** Docstrings short of `.claude/rules/docstrings.md`: `buying.*` (`latest_rate`
  raises `IndexError`, undocumented), `__main__.buy_report_inputs`,
  `report.buy_report_sections`, `build_buy_report`; `price_trend` partial windows at the
  start (`min_periods=1`); `trend_states` (a missing earlier slope reads as "falling,
  slowing"; `IndexError` with fewer than `lag_days + 1` rows).

### Notes

- N1. `price_trend` and `amortise` belong in `skatkis.financial_logic`; `loan_repaid_after`
  and `savings_projection` are general and could move there; `tfsa_full_after` stays.
- N2. Determinism and point in time hold in the code checked (causal windows, prices and
  rate on or before `end`, no clock or randomness).
- N3. No methodology change presented as otherwise: the wallet still weights by score, the
  refactor check shows the outputs unchanged.
- N4. Every `noqa` has a reason; `_buy_list`'s is inaccurate; a dataclass of the trend
  windows would remove PLR0913 in three signatures.
- N5. The steward re-implements LaTeX compilation; `_buy_list_facts` uses a literal 252;
  `[buy_list] text` says "three times" though `rank_ramp` is configurable.
- N6. The trend uses `close`, not adjusted close (record which); `--no-plots` help omits
  the rule-weight CSVs; `_buy` returns 0 when no PDF is written; `_saving_facts` assigns
  `person` twice; `_report`'s signature reformatted with no change; `allocation` counts
  holdings without a target in the total without listing them.
- N7. `openpyxl` is used by no code: record why or drop it.
- N8. `.claude/rules/docstrings.md` paths lack `Toolbox/steward/**`.

### Not checked

`results/` and the PDFs; notebooks; the diffs of `midas/instructions/` and `.claude/`; the
edit to S_202610_006's change file; whether `settings.local.json` is tracked; that
`finances.toml` is untracked; removed tests; VI_202611_004's script; the steward report's
numbers; the index excluding `data/private/` (S_202610_002 does not exist yet).

### Documentation to update (Scribe)

The docstrings of S8, plus `company_portfolio` (person, phases) and `savings_projection`
(raises); the `value_investing/__main__.py` module docstring (`REPORT_TABLES`, the FRED
read); `docs/value_investing_bot_spec.md`: a section on the buy list and price trends (four
weightings and formulas, shown only; trend measures and states; the `buy` command; fixed
purchases never in the wallets); `[buy_list] text` wording to follow `rank_ramp`;
`config/report_steward.toml` placeholders only; `AGENTS.md` and `developer.md` layout with
`Toolbox/steward/` (Secretary); `.claude/rules/docstrings.md` path (Developer).

### Tests to write (Tester)

`price_trend` (hand series, missing trend mean, `from_high`, `from_trend`, `in_range` 0/1/
missing, slope = 252 × ΔEWM, bad prices dropped, no look-ahead); `amortise` (one month, the
cut final payment, growing balance, zero balance); `ramp_weights`; `buy_list` (four
weightings, dip ties and missing place, fixed amounts, USD and shares, weights sum to 1);
`trend_states` (four states, slope = 0, too few rows); `buying` (`latest_rate`,
`next_picks`, `prepare_buy_list` ignores later prices); `__main__` (`--no-plots`, `buy`
keeps only the PDF); `REPORT_TABLES`; `steward.finances.parse_finances`;
`steward.projection` (net worth, allocation, cash flow, property, savings with escalation,
raises and phases, listed, retirement table and its `ValueError`, TFSA room, company
portfolio and assessed loss); `steward.report` (every placeholder resolves; nothing written
outside the folder); `steward.__main__` (output only under `data_dir/private/...`); all
fixtures synthetic.

## Kickoff prompt

Pick up VI_202611_003. Read the agreed approach, update the data if needed, and add the
buy list and the price curves to the S&P 500 report.

## Done when

- The S&P 500 report for 2026-11-19 shows the buy list under both weightings and the
  price curves of the 10 picks and NVIDIA.
