"""
value_investing/holding.py
--------------------------
Buy and hold: a fixed amount at every decision (January and July) into its picks, never sold.

Each decision date, ``amount_usd`` buys the companies picked (``value_investing.
evaluation.ranked_positions``, buy side) at their weights; every purchase (a lot) is
held to ``end`` with dividends reinvested (``adj_close``). The same amount on the same
dates goes into each comparison (the index's benchmark first, then ``BRK-B``). An
investor who starts in a given year buys at every decision from then on, so a scenario
is the set of lots from its start year. ``rule_profile`` compares the rule points of the
picks that beat the index's benchmark since purchase with those of the picks that did
not.

Owns
----
The lots, the value over time per scenario and holder, the scenario summary, the rule
profile of winning and losing picks, and the wallet that also sells.

Must not
--------
Pick companies or weights (``value_investing.evaluation``); define returns
(``skatkis.financial_logic``); plot (``value_investing.plots``).

Public API
----------
BuyAndHold(lots, yearly, paths, summary)
    The results of ``buy_and_hold``.
buy_and_hold(positions, prices, *, compare, amount_usd, start_years, end)
    Lots, value over time and summary per start year.
largest_winners(lots, n)
    The ``n`` companies that put the most dollars ahead of the benchmark.
winner_stress(runs, removed, benchmark)
    The annual return, the benchmark's and the excess of each start year with the
    largest winners removed.
rule_profile(lots, table, rule_ids)
    Dollar-weighted mean points per rule of the picks that beat the benchmark and of
    those that did not.
dollar_view(lots)
    Dollars ahead of the benchmark of the winning and losing picks, and the payoff ratio.
rule_weighting(lots, table, rule_ids)
    Per rule, its weights in the score against how well it told winners from losers.
weighting_quality(check)
    Rank correlation across rules of the weight with the gap and with the correlation.
Managed(trades, paths, summary, contents, holdings, purchases)
    The results of ``buy_and_sell``.
buy_and_sell(positions, shares, prices, *, threshold, amount_usd, start_years, end)
    The same yearly purchases, with holdings that score at or below a threshold sold
    in part and the proceeds reinvested.

Computes
--------
lot value, buy-and-hold value : buy_and_hold
    value(t) = a * L(t) / L(buy) for each lot of a USD bought on its decision date, L
    the ``adj_close`` level; a holder's value is the sum over its lots bought by t.
dollars ahead of the benchmark : buy_and_hold
    ahead = value(end) - a * (1 + b), a the USD invested and b the benchmark's total
    return from purchase to ``end``.
annualised excess of a pick : buy_and_hold
    ((1 + r) / (1 + b))^(1 / Y) - 1, r and b the pick's and the benchmark's total return
    from purchase to ``end``, Y the years between.
money-weighted annual return of a scenario : buy_and_hold
    ``skatkis.financial_logic.money_weighted_return`` of the yearly amounts and the
    value at ``end``.
largest winners : largest_winners
    Per company, Σ ahead over its lots; the ``n`` highest, ties by symbol.
excess of a stress run : winner_stress
    annual_return of the wallet - annual_return of the benchmark, both money-weighted
    (``buy_and_hold`` summary), per start year and number of winners removed.
weighting check, rule information coefficient over picks : rule_weighting
    Per rule: the mean rule weight w_r on the picks' score dates (overall, for the
    picks that beat the benchmark and for the others); gap = mean points of the picks
    that beat it - mean points of the others, each pick weighted by |ahead|
    (dollar-weighted); IC = Spearman correlation across picks of the rule's points and
    the pick's annualised excess.
weighting quality : weighting_quality
    Spearman correlation across rules of w_r with gap and with IC; above 0 the
    weighting favoured the rules that told winners from losers.
share sold, partial sale : buy_and_sell
    Each decision, a holding with score share s <= threshold t sells the fraction
    (t - s) / t of its units at that day's ``adj_close``; the proceeds and
    ``amount_usd`` buy the picks at their weights.
rule profile of winners : rule_profile
    Mean ``<id>_points`` on the score date, separately for picks with annualised excess
    > 0 and <= 0, each pick weighted by |ahead| (dollar-weighted).
dollar view of winners and losers, payoff ratio : dollar_view
    Per group (beat, lagged, all): number of picks, Σ ahead, mean and median ahead;
    payoff ratio = mean ahead of the winners / |mean ahead of the losers|.

Dependency rule
---------------
pandas, ``skatkis.analysis``, ``skatkis.financial_logic`` and ``value_investing``
(``inputs``, ``rules``, ``scoring``).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pandas as pd

from Toolbox.skatkis.analysis import rank_correlation
from Toolbox.skatkis.financial_logic import (
    DAYS_PER_YEAR,
    annualised_relative_return,
    holding_return,
    money_weighted_return,
)
from Toolbox.value_investing.inputs import price_on
from Toolbox.value_investing.rules import pass_column, points_column
from Toolbox.value_investing.scoring import rule_weights

WALLET = "value wallet"
MANAGED = "value wallet with sells"


@dataclass(frozen=True)
class BuyAndHold:
    """The results of ``buy_and_hold``.

    Parameters
    ----------
    lots : pd.DataFrame
        One row per pick bought: ``decision_date``, ``score_date``, ``symbol``,
        ``gics_sector``, ``score``, ``weight``, ``invested_usd``, ``buy_price``,
        ``last_price`` (``close``, split-adjusted), ``total_return``,
        ``benchmark_return``, ``value_usd`` (at ``end``), ``index_usd`` (the same money
        in the benchmark at ``end``), ``ahead_usd`` (``value_usd - index_usd``),
        ``years`` and ``annualised_excess``.
    yearly : pd.DataFrame
        One row per decision: ``decision_date``, ``picks`` (symbols with weights),
        ``invested_usd`` and the value at ``end`` of that year's purchase for the
        wallet (``value_usd``) and for each comparison (``<symbol>_usd``).
    paths : pd.DataFrame
        ``scenario`` (start year), ``holder`` (``value wallet`` or a comparison),
        ``date``, ``invested_usd`` and ``value_usd``, month by month and on ``end``.
    summary : pd.DataFrame
        One row per scenario and holder: ``scenario``, ``holder``, ``invested_usd``,
        ``value_usd``, ``multiple`` and ``annual_return`` (money-weighted).
    """

    lots: pd.DataFrame
    yearly: pd.DataFrame
    paths: pd.DataFrame
    summary: pd.DataFrame


def buy_and_hold(  # noqa: PLR0913  one keyword per setting of the run
    positions: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    compare: Sequence[str],
    amount_usd: float,
    start_years: Sequence[int],
    end: pd.Timestamp,
) -> BuyAndHold:
    """Return the lots, the value over time and the summary of each start year.

    Parameters
    ----------
    positions : pd.DataFrame
        ``ranked_positions`` output; ``side == "buy"`` rows, with ``decision_date``,
        ``score_date``, ``symbol``, ``score``, ``weight`` and ``gics_sector``.
    prices : pd.DataFrame
        Columns ``symbol``, ``date``, ``close``, ``adj_close``, including ``compare``.
    compare : Sequence[str]
        Comparisons bought with the same money on the same dates; the first is the
        benchmark of ``annualised_excess`` (the index's, e.g. ``^SP500TR``).
    amount_usd : float
        Money per decision.
    start_years : Sequence[int]
        First decision year of each scenario.
    end : pd.Timestamp
        Valuation date (the last trading day of the data).

    Returns
    -------
    BuyAndHold
        Lots, paths and summary. A lot without a price at purchase keeps its money in
        cash at its amount.
    """
    lots = positions.loc[
        (positions["side"] == "buy") & (positions["decision_date"] <= end)
    ].copy()
    lots["invested_usd"] = amount_usd * lots["weight"]
    decisions = sorted(pd.Timestamp(d) for d in lots["decision_date"].unique())
    grid = sorted(
        {*pd.date_range(decisions[0], end, freq="ME"), *decisions, pd.Timestamp(end)}
    )
    symbols = pd.concat([lots["symbol"], pd.Series(list(compare))]).drop_duplicates()
    total = price_on(prices, symbols, grid, column="adj_close")
    close = price_on(prices, symbols, [*decisions, end], column="close")
    wide = total.reset_index().pivot_table(
        index="date", columns="symbol", values="adj_close"
    )

    def at(levels: pd.Series, symbol: pd.Series, day: pd.Series) -> pd.Series:
        keys = pd.MultiIndex.from_arrays([symbol.astype("string"), day])
        return pd.Series(levels.reindex(keys).to_numpy(dtype=float), index=symbol.index)

    final = pd.Series(pd.Timestamp(end), index=lots.index)
    benchmark = pd.Series(compare[0], index=lots.index)
    lots["buy_price"] = at(close, lots["symbol"], lots["decision_date"])
    lots["last_price"] = at(close, lots["symbol"], final)
    lots["total_return"] = holding_return(
        at(total, lots["symbol"], lots["decision_date"]),
        at(total, lots["symbol"], final),
    )
    lots["benchmark_return"] = holding_return(
        at(total, benchmark, lots["decision_date"]), at(total, benchmark, final)
    )
    lots["value_usd"] = (lots["invested_usd"] * (1 + lots["total_return"])).fillna(
        lots["invested_usd"]
    )
    lots["years"] = (pd.Timestamp(end) - lots["decision_date"]).dt.days / DAYS_PER_YEAR
    lots["index_usd"] = lots["invested_usd"] * (1 + lots["benchmark_return"])
    lots["ahead_usd"] = lots["value_usd"] - lots["index_usd"]
    lots["annualised_excess"] = [
        _annualised_excess(float(r), float(b), pd.Timestamp(day), pd.Timestamp(end))
        for r, b, day in zip(
            lots["total_return"],
            lots["benchmark_return"],
            lots["decision_date"],
            strict=True,
        )
    ]

    yearly = (
        lots.groupby("decision_date")
        .agg(invested_usd=("invested_usd", "sum"), value_usd=("value_usd", "sum"))
        .reset_index()
    )
    yearly.insert(
        1,
        "picks",
        [
            ", ".join(
                f"{s} {w:.0%}"
                for s, w in zip(part["symbol"], part["weight"], strict=True)
            )
            for _, part in lots.groupby("decision_date", sort=True)
        ],
    )
    for symbol in compare:
        one = pd.Series(symbol, index=yearly.index)
        grown = holding_return(
            at(total, one, yearly["decision_date"]),
            at(total, one, pd.Series(pd.Timestamp(end), index=yearly.index)),
        )
        yearly[f"{symbol}_usd"] = yearly["invested_usd"] * (1 + grown)

    path_frames: list[pd.DataFrame] = []
    rows: list[dict[str, object]] = []
    for start in start_years:
        later = pd.DatetimeIndex(lots["decision_date"]).year >= start
        own = lots.loc[pd.Series(later, index=lots.index)]
        if own.empty:
            continue
        holders = {WALLET: own[["decision_date", "symbol", "invested_usd"]]}
        dates = sorted(own["decision_date"].unique())
        for symbol in compare:
            holders[symbol] = pd.DataFrame(
                {
                    "decision_date": dates,
                    "symbol": symbol,
                    "invested_usd": amount_usd,
                }
            )
        for holder, bought in holders.items():
            path = _value_path(bought, wide, grid)
            path_frames.append(path.assign(scenario=start, holder=holder))
            flows = bought.groupby("decision_date")["invested_usd"].sum()
            value = float(path["value_usd"].iloc[-1])
            rows.append(
                {
                    "scenario": start,
                    "holder": holder,
                    "invested_usd": float(flows.sum()),
                    "value_usd": value,
                    "multiple": value / float(flows.sum()),
                    "annual_return": money_weighted_return(
                        flows, value, pd.Timestamp(end)
                    ),
                }
            )
    columns = ["scenario", "holder", "date", "invested_usd", "value_usd"]
    return BuyAndHold(
        lots=lots.reset_index(drop=True),
        yearly=yearly,
        paths=pd.concat(path_frames, ignore_index=True)[columns],
        summary=pd.DataFrame(rows),
    )


def largest_winners(lots: pd.DataFrame, n: int) -> list[str]:
    """Return the ``n`` companies whose lots put the most dollars ahead of the benchmark.

    Parameters
    ----------
    lots : pd.DataFrame
        ``BuyAndHold.lots`` with ``symbol`` and ``ahead_usd`` (USD).
    n : int
        How many companies; ``0`` gives none.

    Returns
    -------
    list[str]
        Symbols, the largest total ``ahead_usd`` first; ties by symbol.
    """
    totals: dict[str, float] = {}
    for symbol, usd in zip(lots["symbol"], lots["ahead_usd"], strict=True):
        totals[str(symbol)] = totals.get(str(symbol), 0.0) + float(usd)
    ranked = sorted(totals, key=lambda symbol: (-totals[symbol], symbol))
    return ranked[:n]


def winner_stress(
    runs: Mapping[int, BuyAndHold],
    removed: Mapping[int, Sequence[str]],
    benchmark: str,
) -> pd.DataFrame:
    """Return each start year's excess over the benchmark for each number of winners removed.

    Parameters
    ----------
    runs : Mapping[int, BuyAndHold]
        ``buy_and_hold`` of the wallet with that many of the largest winners removed
        from the ranking (``0`` for the wallet as it is).
    removed : Mapping[int, Sequence[str]]
        The symbols removed in each run.
    benchmark : str
        The holder in the summary that the wallet is measured against.

    Returns
    -------
    pd.DataFrame
        ``removed_count``, ``symbols``, ``scenario``, ``wallet_return``,
        ``benchmark_return`` (money-weighted annual returns) and ``excess`` (their
        difference, a fraction a year).
    """
    rows: list[dict[str, object]] = []
    for count, run in sorted(runs.items()):
        by = run.summary.set_index(["scenario", "holder"])["annual_return"]
        for scenario in sorted(run.summary["scenario"].unique()):
            wallet = float(by[(scenario, WALLET)])
            index = float(by[(scenario, benchmark)])
            rows.append(
                {
                    "removed_count": count,
                    "symbols": ", ".join(removed[count]),
                    "scenario": int(scenario),
                    "wallet_return": wallet,
                    "benchmark_return": index,
                    "excess": wallet - index,
                }
            )
    return pd.DataFrame(rows)


def _annualised_excess(
    stock: float, benchmark: float, bought: pd.Timestamp, end: pd.Timestamp
) -> float:
    """Return a pick's annualised return over the benchmark from purchase to ``end``.

    Uses ``skatkis.financial_logic.annualised_relative_return`` on the two growth paths;
    missing when the holding is younger than a day or a return is missing.
    """
    if pd.isna(stock) or pd.isna(benchmark) or end <= bought:
        return float("nan")
    days = [bought, end]
    return annualised_relative_return(
        pd.Series([1.0, 1 + stock], index=days),
        pd.Series([1.0, 1 + benchmark], index=days),
        min_years=0.0,
    )


def _value_path(
    bought: pd.DataFrame, wide: pd.DataFrame, grid: Sequence[pd.Timestamp]
) -> pd.DataFrame:
    """Return the value and money put in of a set of lots on every date of ``grid``."""
    levels = wide.reindex(list(grid))
    value = pd.Series(0.0, index=levels.index)
    invested = pd.Series(0.0, index=levels.index)
    for day, symbol, amount in zip(
        bought["decision_date"], bought["symbol"], bought["invested_usd"], strict=True
    ):
        held = pd.Series(levels.index >= pd.Timestamp(day), index=levels.index)
        series = (
            levels[str(symbol)]
            if str(symbol) in levels
            else pd.Series(float("nan"), index=levels.index)
        )
        # After its last price a lot keeps that price, as in ``buy_and_sell``; a lot
        # without a price on its purchase date stays in cash at its amount.
        start = series.get(pd.Timestamp(day), float("nan"))
        growth = (series / start).ffill().fillna(1.0)
        value += float(amount) * growth.where(held, 0.0)
        invested += float(amount) * held
    return pd.DataFrame(
        {"date": levels.index, "invested_usd": invested, "value_usd": value}
    ).reset_index(drop=True)


def rule_profile(
    lots: pd.DataFrame, table: pd.DataFrame, rule_ids: Sequence[str]
) -> pd.DataFrame:
    """Return the mean points per rule of the winning and the losing picks.

    Parameters
    ----------
    lots : pd.DataFrame
        ``BuyAndHold.lots``.
    table : pd.DataFrame
        The buyability table with ``symbol``, ``date`` and ``<id>_points``.
    rule_ids : Sequence[str]
        Rules to profile.

    Returns
    -------
    pd.DataFrame
        Columns ``rule``, ``group`` (``beat the index`` or ``did not``), ``points``
        (mean, 0 to 5, each pick weighted by the size of its dollars ahead or behind
        the benchmark) and ``picks``; a pick with a missing point is left out of that
        rule's mean.
    """
    columns = [points_column(r) for r in rule_ids]
    graded = lots.merge(
        table[["symbol", "date", *columns]],
        left_on=["symbol", "score_date"],
        right_on=["symbol", "date"],
        how="left",
    )
    graded["group"] = (
        graded["annualised_excess"]
        .gt(0)
        .map({True: "beat the index", False: "did not"})
    )
    rows: list[dict[str, object]] = []
    for group, part in graded.groupby("group"):
        size = part["ahead_usd"].abs()
        for rule_id, column in zip(rule_ids, columns, strict=True):
            rows.append(
                {
                    "rule": rule_id,
                    "group": str(group),
                    "points": _weighted_mean(part[column], size),
                    "picks": len(part),
                }
            )
    return pd.DataFrame(rows)


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    """Return the mean of ``values`` weighted by ``weights``, skipping missing values."""
    known = values.notna() & weights.notna()
    total = float(weights[known].sum())
    if total <= 0:
        return float("nan")
    return float((values[known] * weights[known]).sum()) / total


def dollar_view(lots: pd.DataFrame) -> pd.DataFrame:
    """Return the dollars ahead of the benchmark of the winning and losing picks.

    Parameters
    ----------
    lots : pd.DataFrame
        ``BuyAndHold.lots`` with ``ahead_usd`` and ``annualised_excess``.

    Returns
    -------
    pd.DataFrame
        Rows ``beat``, ``lagged`` and ``all``: ``picks``, ``total_usd`` (Σ ahead),
        ``mean_usd`` and ``median_usd``.
    """
    beat = lots["annualised_excess"] > 0
    rows: list[dict[str, object]] = []
    for name, part in (("beat", lots[beat]), ("lagged", lots[~beat]), ("all", lots)):
        ahead = part["ahead_usd"]
        rows.append(
            {
                "group": name,
                "picks": len(part),
                "total_usd": float(ahead.sum()),
                "mean_usd": float(ahead.mean()),
                "median_usd": float(ahead.median()),
            }
        )
    return pd.DataFrame(rows)


def rule_weighting(
    lots: pd.DataFrame,
    table: pd.DataFrame,
    rule_ids: Sequence[str],
) -> pd.DataFrame:
    """Return, per rule, its weight against how well it told winners from losers.

    Parameters
    ----------
    lots : pd.DataFrame
        ``BuyAndHold.lots`` (``symbol``, ``score_date``, ``annualised_excess``).
    table : pd.DataFrame
        The buyability table: ``symbol``, ``date``, ``<id>_pass`` and ``<id>_points``.
    rule_ids : Sequence[str]
        Rules to check.

    Returns
    -------
    pd.DataFrame
        Columns ``rule``, ``weight`` (mean over the picks' score dates),
        ``weight_beat`` and ``weight_not`` (the same over the picks that beat the S&P
        500 and over the others), ``points_beat``, ``points_not`` (dollar-weighted
        means), ``gap`` (``points_beat - points_not``) and ``ic`` (Spearman
        correlation across picks of points and annualised excess).

    Notes
    -----
    The weights are those of ``value_investing.scoring.rule_weights`` (1 - pass rate
    across the companies on the date), the same as in ``score_binned_weighted``.
    """
    flags = table.set_index(["symbol", "date"])
    weights = rule_weights(flags, [pass_column(r) for r in rule_ids])
    picks = lots.merge(
        table[["symbol", "date", *[points_column(r) for r in rule_ids]]],
        left_on=["symbol", "score_date"],
        right_on=["symbol", "date"],
        how="left",
    )
    beat = picks["annualised_excess"] > 0
    size = picks["ahead_usd"].abs()
    rows: list[dict[str, object]] = []
    for rule_id in rule_ids:
        weight = picks["score_date"].map(weights[pass_column(rule_id)])
        points = picks[points_column(rule_id)]
        both = pd.DataFrame({"p": points, "x": picks["annualised_excess"]}).dropna()
        rows.append(
            {
                "rule": rule_id,
                "weight": float(weight.mean()),
                "weight_beat": float(weight[beat].mean()),
                "weight_not": float(weight[~beat].mean()),
                "points_beat": _weighted_mean(points[beat], size[beat]),
                "points_not": _weighted_mean(points[~beat], size[~beat]),
                "gap": _weighted_mean(points[beat], size[beat])
                - _weighted_mean(points[~beat], size[~beat]),
                "ic": rank_correlation(both["p"], both["x"]),
            }
        )
    return pd.DataFrame(rows)


def weighting_quality(check: pd.DataFrame) -> dict[str, float]:
    """Return the rank correlation across rules of the weight with ``gap`` and ``ic``.

    Above 0, the rules that weigh more were the ones whose points went with the picks
    that did better; below 0, the weighting favoured the wrong rules.
    """
    return {
        "weight_vs_gap": rank_correlation(check["weight"], check["gap"]),
        "weight_vs_ic": rank_correlation(check["weight"], check["ic"]),
    }


@dataclass(frozen=True)
class Managed:
    """The results of ``buy_and_sell``.

    Parameters
    ----------
    trades : pd.DataFrame
        One row per trade: ``scenario``, ``decision_date``, ``symbol``, ``action``
        (``buy`` or ``sell``), ``score_share`` (the 0-to-1 score on the score date),
        ``fraction`` (share of the holding sold; missing for buys) and ``usd``.
    paths : pd.DataFrame
        As ``BuyAndHold.paths``, holder ``value wallet with sells``.
    summary : pd.DataFrame
        As ``BuyAndHold.summary``, holder ``value wallet with sells``.
    contents : pd.DataFrame
        What each scenario's wallet holds over time: ``scenario``, ``date``,
        ``symbol`` (``cash`` for money a missing price left unspent) and
        ``value_usd``, month by month and on each decision date after its trades.
    purchases : pd.DataFrame
        One row per purchase: ``scenario``, ``decision_date``, ``symbol``,
        ``invested_usd``, ``sold_usd`` (what later sales took from this purchase),
        ``kept_usd`` (its value at ``end``), ``total_return`` ((sold + kept) /
        invested - 1, dividends included), ``buy_price`` and ``last_price``
        (``close``, split-adjusted).
    holdings : pd.DataFrame
        What each scenario holds at ``end``: ``scenario``, ``symbol``, ``value_usd``,
        ``score_share`` on the latest score date, and ``sell_fraction``, the share the
        rule would sell at the next decision (0 to keep).
    """

    trades: pd.DataFrame
    paths: pd.DataFrame
    summary: pd.DataFrame
    contents: pd.DataFrame
    holdings: pd.DataFrame
    purchases: pd.DataFrame


class _Levels:
    """``adj_close`` levels on a grid of dates, looked up by day and symbol."""

    def __init__(self, levels: pd.DataFrame) -> None:
        self._matrix = levels.to_numpy(dtype=float)
        self._row = {pd.Timestamp(d): i for i, d in enumerate(levels.index)}
        self._column = {str(c): j for j, c in enumerate(levels.columns)}

    def at(self, day: pd.Timestamp, symbol: str) -> float:
        """Return the level on ``day``; 1 for ``cash``, NaN without a price."""
        if symbol == "cash":
            return 1.0
        if symbol not in self._column:
            return float("nan")
        return float(self._matrix[self._row[day], self._column[symbol]])

    def value(self, day: pd.Timestamp, units: dict[str, float]) -> float:
        """Return the value of ``units`` on ``day``."""
        return sum(u * self.at(day, s) for s, u in units.items())


def _sell_fraction(share: float, threshold: float) -> float:
    """Return the share of a holding to sell: (t - s) / t at or below t, else 0."""
    if pd.isna(share) or share > threshold:
        return 0.0
    return (threshold - share) / threshold


def buy_and_sell(  # noqa: PLR0913  one keyword per setting of the run
    positions: pd.DataFrame,
    shares: pd.Series,
    prices: pd.DataFrame,
    *,
    threshold: float,
    amount_usd: float,
    start_years: Sequence[int],
    end: pd.Timestamp,
) -> Managed:
    """Return the yearly wallet that also sells holdings scoring at or below ``threshold``.

    Parameters
    ----------
    positions : pd.DataFrame
        ``ranked_positions`` output; ``side == "buy"`` rows with ``decision_date``,
        ``score_date``, ``symbol`` and ``weight``.
    shares : pd.Series
        The 0-to-1 score (``score_weighted_share``), indexed (``symbol``, ``date``).
    prices : pd.DataFrame
        Columns ``symbol``, ``date``, ``adj_close``.
    threshold : float
        A holding with score share at or below it is sold in part (0.4).
    amount_usd : float
        New money per decision.
    start_years : Sequence[int]
        First decision year of each scenario.
    end : pd.Timestamp
        Valuation date.

    Returns
    -------
    Managed
        Trades, value over time, summary and current holdings per start year.

    Notes
    -----
    Holdings are counted in units of ``adj_close``, so dividends stay invested. At each
    decision the sales come first, then the proceeds and ``amount_usd`` buy the picks.
    A holding without a score on the score date is kept; money a missing price leaves
    unspent stays in cash. Only the new money counts as money put in; the
    money-weighted return uses it and the value at ``end``.
    """
    buys = positions.loc[
        (positions["side"] == "buy") & (positions["decision_date"] <= end)
    ]
    decisions = sorted(pd.Timestamp(d) for d in buys["decision_date"].unique())
    grid = sorted(
        {*pd.date_range(decisions[0], end, freq="ME"), *decisions, pd.Timestamp(end)}
    )
    levels = _Levels(
        price_on(prices, buys["symbol"].drop_duplicates(), grid, column="adj_close")
        .reset_index()
        .pivot_table(index="date", columns="symbol", values="adj_close")
        .reindex(grid)
        .ffill()
    )
    trades: list[dict[str, object]] = []
    path_frames: list[pd.DataFrame] = []
    rows: list[dict[str, object]] = []
    held: list[pd.DataFrame] = []
    content_frames: list[pd.DataFrame] = []
    lot_frames: list[pd.DataFrame] = []
    for start in start_years:
        units: dict[str, float] = {}
        snapshots: dict[pd.Timestamp, dict[str, float]] = {}
        for day in (d for d in decisions if d.year >= start):
            today = buys[buys["decision_date"] == day]
            score_date = pd.Timestamp(today["score_date"].iloc[0])
            units["cash"] = units.get("cash", 0.0) + amount_usd
            for symbol in [s for s in units if s != "cash"]:
                share = float(shares.get((symbol, score_date), float("nan")))
                fraction = _sell_fraction(share, threshold)
                price = levels.at(day, symbol)
                if fraction == 0 or pd.isna(price):
                    continue
                usd = units[symbol] * fraction * price
                units[symbol] -= units[symbol] * fraction
                units["cash"] += usd
                trades.append(
                    _trade(
                        start,
                        day,
                        symbol,
                        action="sell",
                        share=share,
                        fraction=fraction,
                        usd=usd,
                    )
                )
            spend = units["cash"]
            for symbol, weight in zip(today["symbol"], today["weight"], strict=True):
                price = levels.at(day, str(symbol))
                if pd.isna(price):
                    continue
                usd = spend * float(weight)
                units[str(symbol)] = units.get(str(symbol), 0.0) + usd / price
                units["cash"] -= usd
                share = float(shares.get((str(symbol), score_date), float("nan")))
                trades.append(
                    _trade(
                        start,
                        day,
                        str(symbol),
                        action="buy",
                        share=share,
                        fraction=float("nan"),
                        usd=usd,
                    )
                )
            snapshots[day] = dict(units)
        if not snapshots:
            continue
        path = _managed_path(snapshots, grid, levels, amount_usd)
        path_frames.append(path.assign(scenario=start, holder=MANAGED))
        content_frames.append(_contents(snapshots, grid, levels).assign(scenario=start))
        rows.append(_summary_row(start, path, amount_usd, snapshots, end))
        held.append(
            _current(start, units, levels, shares=shares, threshold=threshold, end=end)
        )
        own = [t for t in trades if t["scenario"] == start]
        lot_frames.append(
            _purchases(pd.DataFrame(own), levels, end).assign(scenario=start)
        )
    columns = ["scenario", "holder", "date", "invested_usd", "value_usd"]
    return Managed(
        trades=pd.DataFrame(trades),
        paths=pd.concat(path_frames, ignore_index=True)[columns],
        summary=pd.DataFrame(rows),
        contents=pd.concat(content_frames, ignore_index=True)[
            ["scenario", "date", "symbol", "value_usd"]
        ],
        holdings=pd.concat(held, ignore_index=True),
        purchases=_with_prices(pd.concat(lot_frames, ignore_index=True), prices, end),
    )


def _purchases(
    trades: pd.DataFrame, levels: _Levels, end: pd.Timestamp
) -> pd.DataFrame:
    """Return each purchase with what later sales took from it and what it keeps.

    A sale sells the same share of every unit of the company held, so each earlier
    purchase of that company gives up that share of its remaining units at the sale's
    price; purchases on the sale's own date come after it and are untouched.
    """
    buys = trades[trades["action"] == "buy"]
    sells = trades[trades["action"] == "sell"]
    rows: list[dict[str, object]] = []
    for day, symbol, usd in zip(
        buys["decision_date"], buys["symbol"], buys["usd"], strict=True
    ):
        bought = pd.Timestamp(day)
        units = float(usd) / levels.at(bought, str(symbol))
        sold = 0.0
        mask = (sells["symbol"] == symbol) & (sells["decision_date"] > bought)
        later = sells.loc[pd.Series(mask.to_numpy(), index=sells.index)]
        for when, fraction in zip(
            later["decision_date"].tolist(), later["fraction"].tolist(), strict=True
        ):
            sold += units * float(fraction) * levels.at(pd.Timestamp(when), str(symbol))
            units *= 1 - float(fraction)
        kept = units * levels.at(pd.Timestamp(end), str(symbol))
        rows.append(
            {
                "decision_date": bought,
                "symbol": str(symbol),
                "invested_usd": float(usd),
                "sold_usd": sold,
                "kept_usd": kept,
                "total_return": (sold + kept) / float(usd) - 1,
            }
        )
    return pd.DataFrame(rows)


def _with_prices(
    purchases: pd.DataFrame, prices: pd.DataFrame, end: pd.Timestamp
) -> pd.DataFrame:
    """Add the split-adjusted ``close`` at purchase and at ``end`` to each purchase."""
    days = sorted({*purchases["decision_date"], pd.Timestamp(end)})
    close = price_on(
        prices, purchases["symbol"].drop_duplicates(), days, column="close"
    )

    def at(day: pd.Series) -> pd.Series:
        keys = pd.MultiIndex.from_arrays([purchases["symbol"].astype("string"), day])
        return pd.Series(
            close.reindex(keys).to_numpy(dtype=float), index=purchases.index
        )

    return purchases.assign(
        buy_price=at(purchases["decision_date"]),
        last_price=at(pd.Series(pd.Timestamp(end), index=purchases.index)),
    )


def _trade(  # noqa: PLR0913  one field per column of the trade table
    start: int,
    day: pd.Timestamp,
    symbol: str,
    *,
    action: str,
    share: float,
    fraction: float,
    usd: float,
) -> dict[str, object]:
    """Return one row of the trade table."""
    return {
        "scenario": start,
        "decision_date": day,
        "symbol": symbol,
        "action": action,
        "score_share": share,
        "fraction": fraction,
        "usd": usd,
    }


def _managed_path(
    snapshots: dict[pd.Timestamp, dict[str, float]],
    grid: Sequence[pd.Timestamp],
    levels: _Levels,
    amount_usd: float,
) -> pd.DataFrame:
    """Return the value and money put in on every grid date from the first decision."""
    days = sorted(snapshots)
    dates = [d for d in grid if d >= days[0]]
    values: list[float] = []
    invested: list[float] = []
    for day in dates:
        done = [d for d in days if d <= day]
        values.append(levels.value(day, snapshots[done[-1]]))
        invested.append(amount_usd * len(done))
    return pd.DataFrame({"date": dates, "invested_usd": invested, "value_usd": values})


def _contents(
    snapshots: dict[pd.Timestamp, dict[str, float]],
    grid: Sequence[pd.Timestamp],
    levels: _Levels,
) -> pd.DataFrame:
    """Return each holding's value on every grid date from the first decision.

    On a decision date the holdings are those after its sales and purchases.
    """
    days = sorted(snapshots)
    rows: list[dict[str, object]] = []
    for day in (d for d in grid if d >= days[0]):
        book = snapshots[[d for d in days if d <= day][-1]]
        rows.extend(
            {"date": day, "symbol": symbol, "value_usd": held * levels.at(day, symbol)}
            for symbol, held in book.items()
            if held > 0
        )
    return pd.DataFrame(rows)


def _summary_row(
    start: int,
    path: pd.DataFrame,
    amount_usd: float,
    snapshots: dict[pd.Timestamp, dict[str, float]],
    end: pd.Timestamp,
) -> dict[str, object]:
    """Return the scenario's summary: money put in, value, multiple and annual return."""
    flows = pd.Series(amount_usd, index=sorted(snapshots))
    value = float(path["value_usd"].iloc[-1])
    return {
        "scenario": start,
        "holder": MANAGED,
        "invested_usd": float(flows.sum()),
        "value_usd": value,
        "multiple": value / float(flows.sum()),
        "annual_return": money_weighted_return(flows, value, pd.Timestamp(end)),
    }


def _current(  # noqa: PLR0913  one argument per input of the valuation
    start: int,
    units: dict[str, float],
    levels: _Levels,
    *,
    shares: pd.Series,
    threshold: float,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Return what a scenario holds at ``end`` and what the rule would sell of it."""
    dates = shares.index.get_level_values("date")
    latest = pd.Timestamp(dates[dates <= end].max())
    rows: list[dict[str, object]] = []
    for symbol, held in units.items():
        if symbol == "cash" or held <= 0:
            continue
        share = float(shares.get((symbol, latest), float("nan")))
        rows.append(
            {
                "scenario": start,
                "symbol": symbol,
                "value_usd": held * levels.at(pd.Timestamp(end), symbol),
                "score_date": latest,
                "score_share": share,
                "sell_fraction": _sell_fraction(share, threshold),
            }
        )
    return pd.DataFrame(rows).sort_values("value_usd", ascending=False)
