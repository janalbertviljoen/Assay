# Valuation spread: hold the S&P 500 or hold USD cash (diagnostic)

Fixed 2026-11-22, before any result was seen. Results and their reading:
`midas/toolbox/value_investing/notes.md`, "Valuation spread as a sell-everything signal".

Run from the repository root:
`.venv/bin/python -m Toolbox.SandBox.valuation_spread.run data/raw/library/2026-11-22`

## Amended after the Warden's review (2026-11-22, VI_202611_005)
The first run traded each month's signal on a return that began half a month before the
signal was known (Shiller's prices are monthly averages): a look-ahead. Fixed, and the
results rerun and recorded; the specifications, percentile and horizon are unchanged.
- **Timing:** the signal at the end of month t trades `R_{t+1}` (mid-month t+1 to mid-month
  t+2); cash earns the mean of the T-bill rates of the two months it spans.
- **Months:** complete months only (to 2026-10 in this snapshot); returns end with the last
  one whose end price and T-bill rates are complete (2026-08).
- **Bootstrap:** every block start can be drawn, the last included.
- Shared code: `Toolbox/SandBox/strategy_library/series.py`.

## Data (snapshot data/raw/library/2026-11-22)
- Shiller ie_data.xls (current, shillerdata.com): monthly S&P composite price P (monthly
  average of daily closes), dividends D and earnings E (trailing 12 months), GS10, CAPE.
- Fama-French F-F_Research_Data_Factors: monthly RF (1-month T-bill), from 1926-07.

## Signal (known at month end t)
- Earnings are lagged 3 months for publication: EY_t = E_{t-3} / P_t.
- Main: S_t = EY_t - GS10_t / 100 (earnings yield less the nominal 10-year yield).
- Variant (counted): Shiller's excess CAPE yield, lagged 3 months in full (ECY_{t-3}).

## Rule
- Hold the index in month t+1 if S_t >= the 20th percentile of S over 1871..t (expanding,
  only data known at t); otherwise hold cash earning RF.
- 0.5% cost on each switch.

## Test
- Period: 1926-07 to the last month with RF and a return.
- Equity monthly total return: (P_{t+1} + D_t / 12) / P_t - 1.
- Measures: annualised return, volatility, maximum drawdown, share of time in cash, the
  exit episodes; rolling 36-month paired difference (rule less buy-and-hold) with a
  moving-block bootstrap (36-month blocks, 2000 draws, 90% band).
- Predictive check: out-of-sample R^2 (Campbell-Thompson) of S_t for the next 36-month
  excess return against the expanding historical mean; regressions fitted only on windows
  closed by t.
- Today's reading: the latest S and its percentile in history.

## Count
Two specifications tried (main, variant). Percentile 20 and horizon 36 months fixed.

## Known biases
Shiller prices are monthly averages (smooths returns and drawdowns; the timing above
removes the look-ahead they caused); missing recent dividends are carried forward; pre-1926 earnings are
reconstructed (Cowles); the most recent earnings months may be estimates; one market (the
US, the survivor among markets); no taxes; costs are a flat assumption.
