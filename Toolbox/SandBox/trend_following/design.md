# Trend following on the S&P 500: hold the index or USD cash (diagnostic)

Fixed 2026-11-22, before any result was seen. Run from the repository root:
`.venv/bin/python -m Toolbox.SandBox.trend_following.run data/raw/library/2026-11-22` and
`.venv/bin/python -m Toolbox.SandBox.trend_following.run_tech data/interim/trend_tech/2026-11-22 data/raw/library/2026-11-22`
(after `python -m Toolbox.SandBox.trend_following.fetch_tech data 2026-11-22`).

## Amended after the Warden's review (2026-11-22, VI_202611_005)
The first run had a half-month look-ahead on Shiller's averaged prices, a partial month
read as the current signal, an end date set by the T-bill file, and a control on longer
dates than the series it controls. Fixed, rerun and recorded; rules, windows and the count
are unchanged.
- **Shiller timing:** the signal at the end of month t trades `R_{t+1}` (mid-month t+1 to
  mid-month t+2); cash earns the mean of the T-bill rates of the two months it spans. Rule
  B compares the returns spanning mid t-12 to mid t with the T-bills of months t-11..t.
- **Month-end timing (Yahoo):** the signal at the close of month t trades month t+1 and
  earns month t+1's T-bill; rule B compares months t-11..t with the T-bills of t-11..t.
- **Months:** complete months only (to 2026-10 in this snapshot); the last return month is
  2026-09 (Yahoo) or the last whose T-bill months are complete (Shiller, 2026-08). A partial
  month is printed as such, never as a signal.
- **Control:** SPY starts at the latest first month of QQQ, XLK and NVDA.
- **Falls,** by the month the return is earned: 1929-32 (1929-09..1932-06), 1937-38
  (1937-03..1938-03), 1973-74 (1973-01..1974-09), 2000-02 (2000-04..2002-09), 2007-09
  (2007-11..2009-02), 2020 (2020-02..2020-03), 2022 (2022-01..2022-09).
- **Bootstrap:** every block start can be drawn, the last included.
- Shared code: `Toolbox/SandBox/strategy_library/series.py`.

Direction (the library): Hurst, Ooi and Pedersen (2017) find time-series momentum profitable
in every decade since 1880 and strongest in equity bear markets; Moskowitz, Ooi and
Pedersen (2012) find it in all 58 futures markets, with persistence over 1 to 12 months
that partly reverses later. Dow theory (Hamilton 1922) is the same idea in words.

## Data (snapshot data/raw/library/2026-11-22)
Shiller ie_data.xls: monthly S&P composite price P (monthly average of daily closes) and
dividends D. Fama-French: monthly RF (1-month T-bill), from 1926-07.

## Rules (signal at month end t, held over month t+1)
- A, moving average: hold the index if P_t is above the average of P over t-9..t (the
  10-month average); otherwise cash earning RF.
- B, time-series momentum: hold the index if its total return over the last 12 months
  exceeds the T-bill return over the same months; otherwise cash.
- 0.5% cost on each switch.

## Test
- Period 1926-07 to the last month with RF and a return; equity total return
  (P_{t+1} + D_t / 12) / P_t - 1, as in the valuation-spread test.
- Measures: annualised return, volatility, maximum drawdown, share of time in cash,
  switches; the monthly paired difference with a moving-block bootstrap (36-month blocks,
  2000 draws, 90% band).
- Probes (quant.md 15): the two halves 1926-1975 and 1976-2026; the worst-case loss of
  rule and index in the major falls (1929-32, 1937-38, 1973-74, 2000-02, 2007-09, 2020,
  2022).

## Count
Two specifications (A, B). Window lengths fixed by the literature (10 and 12 months).

## Second test: technology and Nvidia (fixed 2026-11-22, before the fetch)
- Data: Yahoo daily prices through `market_data.sources.prices.load_chart` (snapshot
  `data/raw/yahoo_1d/`, as-of 2026-11-22), fetched by `fetch_tech.py`: QQQ (Nasdaq-100
  fund), XLK (S&P technology sector fund), NVDA, and SPY (S&P 500 fund) as the control on
  the same dates. `adj_close` (dividends reinvested), month-end closes, not averages.
- Rules A and B exactly as above, on each series; cash at the Fama-French T-bill rate;
  0.5% per switch. Period: from each series' first 12 months to 2026-09.
- Same measures; falls: 2000-02, 2007-09, 2020, 2022.
- Count: two rules on three new series (six), the control not counted.
- Known limit: about 27 years, four big falls; a single share (NVDA) is far more volatile
  than an index, so its result is a case, not evidence.

## Known biases
Monthly averaged prices smooth the signal and the drawdowns (a real trader sees month-end
closes; the timing above removes the look-ahead they caused); missing recent Shiller
dividends are carried forward; the bands are not adjusted for the ten specifications tried
across this change; one market; no taxes (a sale in a taxable account realises capital gains); costs are a flat
assumption; trend rules are known to lose in sharp V-shaped recoveries.
