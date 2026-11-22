# S_202610_006: Multi-asset portfolio backtest engine

| Field | Value |
|---|---|
| Status | in discussion |
| Priority | high |
| Kind | new capability |
| Depends on | S_202610_001; spec §9.2 (bottom ten) and §9.4 (wallet contract) |
| Raised | 2026-10-31 |

## Description

The wallet (`trade_wallet.update_wallet`) simulates one asset, row by row, buying or
selling a fraction of cash or volume on each signal, with no costs. The value-investing
strategies (spec §5) need a portfolio: ten names held at once, rebalanced quarterly,
held until they drop out of the top N, or sold after a 50% gain or two years, with
explicit transaction costs.

## Objective (user, 2026-10-31)

The user holds mostly the S&P 500 and wants to put about 10% of new investments into a
value-investing sleeve. The sleeve aims to beat the S&P 500 by about 2% a year, and
not doing worse is the minimum (user, 2026-11-01), so the benchmark is the S&P 500
itself (total return, e.g. SPY with dividends) and the primary measures are
out-of-sample excess return over it and how often and how far it trails it over rolling
periods, with drawdown and turnover alongside. Results may also be reported as CPI + x%.
The wallet tracks many strategy combinations side by side so they can be compared and
optimised on that measure.

## Approach (to discuss)

A new engine in `Toolbox/skatkis/backtest/`, alongside the existing single-asset wallet
(which stays, unchanged, for the sandbox):

- input contract: a ticker × date panel of target weights (or orders) produced by a
  strategy, plus a price panel;
- pure, vectorised accounting: positions, cash, turnover, costs, portfolio value, and
  the S&P 500 total-return benchmark over the same dates and cash flows;
- quarterly trades only (rebalance dates from config), replacing the VWAP deviation
  signals of the BTC wallet;
- many strategy combinations run side by side, each summarised by excess return over
  the S&P 500 in-sample and out-of-sample (walk-forward, spec §3.7);
- strategies as a registry in the tool (`Toolbox/value_investing/strategies.py`), each a
  function from the quarterly ranking to target weights;
- performance metrics (return, drawdown, Sharpe, turnover) in `skatkis.financial_logic`,
  shared with the existing `summarise`.

## Proposed by the user (2026-10-31)

- **Relative wealth against the index.** Results are normalised to what the same
  deposits would be worth in the S&P 500 total-return index, for example
  $W_t = V_t / V^{\text{S\&P}}_t$, where $V_t$ is the portfolio value on day $t$ and
  $V^{\text{S\&P}}_t$ the value of the same deposits, on the same dates, invested in
  `^SP500TR`. Above 1 the strategy beat an index fund. Both value investing and
  `hand_o_midas` strategies are compared on it.

- **Aggregate metrics against the benchmark** (user, 2026-10-31). Each model portfolio
  gets aggregate metrics such as its P/E (computed from its holdings), compared with the
  same metrics of the S&P 500 imported from an index source. Aggregates use the
  portfolio weights, each company's share of the portfolio's value (user, same day).

- **Sell when a holding drops below the threshold** (user, 2026-10-31). A company
  already in the wallet whose score falls below the buy threshold is sold, using the
  short approach (VI_202610_003 and VI_202610_004 measure a sell as gaining when the
  stock lags the index). It builds on the buy-and-hold wallet of VI_202610_006 and on
  the trade logic of the single-asset wallet (`skatkis.backtest.wallet`). To discuss:
  which threshold (the buy cut-off or a lower one, to avoid selling and buying back on
  small moves), whether "sell" means selling the holding or also shorting it, and
  where the money goes after a sale. Decided the same day (user): selling the holding
  only, no short; each January a holding whose score on 0 to 1 is at or below 0.4
  sells the share (0.4 - s) / 0.4 of itself, and the proceeds are reinvested with the
  new 100 USD in that year's picks. Built first in the value tool's report
  (VI_202610_006).

## Open decisions (user)

- How a ratio is aggregated with the weights. Proposed: a weighted harmonic mean for
  price ratios, $\text{P/E}_{\text{portfolio}} = 1 / \sum_i (w_i / \text{P/E}_i)$,
  where $w_i$ is company $i$'s weight, which equals total value over total earnings; a
  weighted arithmetic mean of P/Es is pulled up by one company with tiny earnings
  (Coca-Cola's P/E of about 160 in 2018). Companies with zero or negative earnings
  need a rule (left out, or counted with their losses).

- Spec §9.4: wallet input contract: signals, target weights (proposed) or orders.
- Spec §9.2: bottom ten as avoid/sell only, or shorted?
- Cost model: fixed basis points per trade (proposed), or per-share commission plus
  spread? Proposal for later, not to build now (user, 2026-11-16): costs and tax
  depend on the member's platform and country, so they are inputs, not constants:
  - a **platform profile** in config: commission (a percentage with a minimum per
    trade), spread or slippage in basis points, currency conversion and custody fees;
    EasyEquities USD the first example, plain basis points per trade the default;
  - a **tax profile**: dividend withholding (for a South African resident holding US
    shares normally 15% under the treaty, to be checked), capital gains tax on sales,
    and the account type (a tax-free account is exempt); rates are the member's own
    input, never a rate Midas recommends;
  - the **benchmark charged the same way**: `^SP500TR` assumes gross dividends at no
    cost, while a member holds the index through an ETF with its fee, withholding and
    trading costs;
  - a **sensitivity table** in the report: excess return at 0, 25, 50 and 100 basis
    points, before and after tax.

  Today no layer charges costs or tax (`skatkis.backtest.wallet`,
  `value_investing.ledger`, the BTC harness), against the spec (§ overfitting, "net of
  explicit transaction costs") and `researcher.md`; the report states it. A methodology
  change: Buffett's letters first (2005, "helpers" and frictional costs).
- Confirm the temporary dependency of `skatkis.midas.server` on the sandbox harness
  (from S_202610_001), which this change removes when the lab tools move to the
  portfolio engine.

## Done when

- Agreed and designed (`design/S_202610_006-portfolio-backtest-engine.md`) before any
  code.
