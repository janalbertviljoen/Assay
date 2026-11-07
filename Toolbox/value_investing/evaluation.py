"""
value_investing/evaluation.py
-----------------------------
A paper test of the buyability score: yearly buy and sell signals held over horizons.

At the first trading day of each year, every company whose latest known score is at or
above the buy threshold gets a 100 USD buy, and every company at or below the sell
threshold a 100 USD sell, held without rebalancing or costs for each horizon. A buy
succeeds when the stock beats ``^SP500TR`` over the window; a sell when it does worse
(selling the stock and holding the index). The positions summed per decision year form
a paper wallet, and the model score is the annualised excess return of the 1-year buy
wallet chained over the years. The rank correlation of score with forward excess return
per horizon shows how far ahead the score says anything. Results are in-sample
diagnostics for the decision years before ``held_out_from`` and held-out after it.

Owns
----
Decision dates, signals, holdings, paper wallets, the model score and the rank
correlation per horizon.

Must not
--------
Compute the score (``value_investing.scoring``); define returns
(``skatkis.financial_logic``); trade, size or rebalance a portfolio
(``skatkis.backtest``); plot (``value_investing.plots``).

Public API
----------
Evaluation
    The settings of ``[evaluation]`` in ``config/rules.toml``.
decision_dates(trading_days, *, first_year, months)
    The first trading day of each decision month (January by default).
signals(table, dates, settings)
    Buy and sell signals per decision date.
holdings(signal_table, prices, settings, *, benchmark, end)
    Each signal held over each horizon, against the benchmark.
wallets(holding_table, settings)
    The positions summed per decision date, horizon and side.
model_score(wallet_table, settings)
    Annualised excess return of the chained buy wallet, per period.
chained_score(path)
    Annualised excess return of any yearly wallet path, per period.
Wallet
    The settings of the ranked long-short wallet (``[wallet]``).
book_weights(scores, wallet, *, side)
    The weights of the companies bought or sold on one date.
ranked_positions(table, dates, wallet)
    The ranked wallet's positions on each decision date.
ranking(table, day, *, by, columns)
    Every scored company on the latest rebalance date, best to worst by one column.
ranked_wallet(positions, prices, wallet, settings, *, benchmark)
    The ranked wallet's return and excess per decision.
correlation_curve(table, prices, dates, settings, *, benchmark)
    Rank correlation of score and forward excess return per horizon.
short_path(path)
    A ranked wallet's sell book as a model path of its own.

Computes
--------
buy excess, sell excess : holdings
    Buy: e = r - b; sell: e = b - r, with r the stock's and b ``^SP500TR``'s holding
    return over the same window. A buy's value is P(1 + r), a sell's (a short) P(1 - r),
    P the position in USD.
paper wallet return, hit rate, long-short spread : wallets
    Wallet return = Σ value / Σ invested - 1 (equal weights); excess = mean e; hit rate
    = share of positions with e > 0; long-short = mean r of buys - mean r of sells.
model score, annualised excess of the buy wallet : model_score
    With W(k) = Π (1 + wallet return) and B(k) = Π (1 + b) over the decision years up to
    k at the score horizon: (W / B)^(1 / Y) - 1, Y the years from the first decision to
    the last window's end.
ranked book weights : book_weights
    Exactly the ``names`` highest (buy) or lowest (sell) scores; a tie at the cut-off is
    broken by symbol.
    ``score``: buy w = s / Σ s over the bought companies, sell equal
    weights; ``rank``: the rank weights, tied companies sharing the mean of the weights
    of the ranks they span, normalised to sum 1. Equal weights when the sum is 0.
ranking of the index : ranking
    All companies with a value in column ``by`` on the latest rebalance date on or
    before ``day``, sorted by it from the highest, ties by symbol; ``rank`` counts from 1
    in that order.
ranked wallet excess : ranked_wallet
    Per book, e = Σ a e_i / A, with a each position's USD, e_i its excess (buy r - b,
    sell b - r) and A the book's money; the wallet is the buy book: wallet return = b +
    e_buy, the index plus the excess. The sell book's e is reported beside it.
short book return : short_path
    The sell book's return as a model: b + e_sell, the index plus the sell book's excess.
information coefficient by horizon, correlation wavelength : correlation_curve
    Per date and horizon h, the Spearman correlation across companies of score and
    r - b over h months; averaged per period.

Dependency rule
---------------
numpy, pandas, ``skatkis.analysis``, ``skatkis.financial_logic`` and
``value_investing.inputs``.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from Toolbox.skatkis.analysis import rank_correlation
from Toolbox.skatkis.financial_logic import annualised_relative_return
from Toolbox.value_investing.inputs import window_returns

SIDES = ("buy", "sell")


@dataclass(frozen=True)
class Evaluation:
    """The settings of ``[evaluation]`` in ``config/rules.toml``.

    Parameters
    ----------
    first_year : int
        First decision year.
    held_out_from : int
        First decision year of the held-out period.
    buy_threshold, sell_threshold : float
        Buy when score >= the buy threshold, sell when score <= the sell threshold.
    position_usd : float
        Money per position.
    horizons_months : tuple[int, ...]
        Holding periods.
    score_horizon_months : int
        Horizon of the model score.
    correlation_max_months : int
        Longest horizon of the rank correlation curve.
    min_companies : int
        Fewest companies for a rank correlation on a date (``[score]``).
    """

    first_year: int
    held_out_from: int
    buy_threshold: float
    sell_threshold: float
    position_usd: float
    horizons_months: tuple[int, ...]
    score_horizon_months: int
    correlation_max_months: int
    min_companies: int

    def period(self, day: pd.Timestamp) -> str:
        """Return ``in-sample`` or ``held-out`` for a decision date."""
        return "held-out" if day.year >= self.held_out_from else "in-sample"


def decision_dates(
    trading_days: Sequence[pd.Timestamp],
    *,
    first_year: int,
    months: Sequence[int] = (1,),
) -> list[pd.Timestamp]:
    """Return the first of ``trading_days`` in each of ``months``, from ``first_year``.

    ``months`` defaults to January only: one decision a year.
    """
    days = pd.Series(sorted(pd.DatetimeIndex(list(trading_days))))
    days = days[(days.dt.year >= first_year) & days.dt.month.isin(list(months))]
    periods = days.dt.year * 100 + days.dt.month
    return [pd.Timestamp(d) for d in days.groupby(periods).min()]


def signals(
    table: pd.DataFrame, dates: Sequence[pd.Timestamp], settings: Evaluation
) -> pd.DataFrame:
    """Return the buy and sell signals on each decision date.

    Parameters
    ----------
    table : pd.DataFrame
        The buyability table (``symbol``, ``date``, ``score``).
    dates : Sequence[pd.Timestamp]
        Decision dates.
    settings : Evaluation
        Thresholds.

    Returns
    -------
    pd.DataFrame
        Columns ``decision_date``, ``score_date`` (the latest rebalance date on or before
        it), ``symbol``, ``score``, ``side`` (``buy`` or ``sell``); companies without a
        score or between the thresholds have no row.
    """
    scored = sorted(pd.Timestamp(d) for d in table["date"].unique())
    frames: list[pd.DataFrame] = []
    for day in dates:
        known = [d for d in scored if d <= day]
        if not known:
            continue
        own = table.loc[table["date"] == known[-1]].dropna(subset=["score"])
        side = pd.Series(pd.NA, index=own.index, dtype="string")
        side[own["score"] >= settings.buy_threshold] = "buy"
        side[own["score"] <= settings.sell_threshold] = "sell"
        frames.append(
            pd.DataFrame(
                {
                    "decision_date": day,
                    "score_date": known[-1],
                    "symbol": own["symbol"],
                    "score": own["score"],
                    "side": side,
                }
            ).dropna(subset=["side"])
        )
    return pd.concat(frames, ignore_index=True)


def holdings(
    signal_table: pd.DataFrame,
    prices: pd.DataFrame,
    settings: Evaluation,
    *,
    benchmark: str,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Return every signal held over every horizon, against the benchmark.

    Parameters
    ----------
    signal_table : pd.DataFrame
        ``signals`` output.
    prices : pd.DataFrame
        Columns ``symbol``, ``date``, ``adj_close``, including ``benchmark``.
    settings : Evaluation
        Horizons and position size.
    benchmark : str
        Total-return benchmark symbol (``^SP500TR``).
    end : pd.Timestamp
        Last date with prices; windows ending later are left out.

    Returns
    -------
    pd.DataFrame
        The signal columns plus ``horizon_months``, ``end_date``, ``stock_return``,
        ``benchmark_return``, ``value``, ``benchmark_value``, ``excess``, ``beat``. A
        position without a price at its start or end (e.g. a company not yet listed)
        has no row.
    """
    frames: list[pd.DataFrame] = []
    for months in settings.horizons_months:
        ends = signal_table["decision_date"] + pd.DateOffset(months=months)
        part = signal_table.assign(horizon_months=months, end_date=ends)[ends <= end]
        returns = window_returns(
            prices,
            pd.MultiIndex.from_arrays(
                [part["symbol"].astype("string"), part["decision_date"]],
                names=["symbol", "date"],
            ),
            benchmark=benchmark,
            months=months,
        )
        frames.append(
            part.assign(
                stock_return=returns["own_return"].to_numpy(),
                benchmark_return=returns["benchmark_return"].to_numpy(),
            )
        )
    held = pd.concat(frames, ignore_index=True)
    stock, index = held["stock_return"], held["benchmark_return"]
    buy = held["side"] == "buy"
    size = settings.position_usd
    held = held.assign(
        value=size * (1 + stock.where(buy, -stock)),
        benchmark_value=size * (1 + index),
        excess=(stock - index).where(buy, index - stock),
    )
    held["beat"] = held["excess"] > 0
    return held.dropna(subset=["stock_return", "benchmark_return"]).reset_index(
        drop=True
    )


def wallets(holding_table: pd.DataFrame, settings: Evaluation) -> pd.DataFrame:
    """Return the positions summed per decision date, horizon and side.

    Parameters
    ----------
    holding_table : pd.DataFrame
        ``holdings`` output.
    settings : Evaluation
        For the period label.

    Returns
    -------
    pd.DataFrame
        Columns ``decision_date``, ``period``, ``horizon_months``, ``end_date``,
        ``side`` (``buy``, ``sell``, ``long_short``), ``positions``, ``invested``,
        ``value``, ``benchmark_value``, ``stock_return`` (mean of the stocks),
        ``wallet_return``, ``benchmark_return``, ``excess``, ``hit_rate``. The
        ``long_short`` row holds the spread of the buys' mean return over the sells' in
        ``excess`` and has no money columns.
    """
    keys = ["decision_date", "horizon_months", "end_date", "side"]
    grouped = holding_table.groupby(keys)
    result = pd.DataFrame(
        {
            "positions": grouped.size(),
            "value": grouped["value"].sum(),
            "benchmark_value": grouped["benchmark_value"].sum(),
            "stock_return": grouped["stock_return"].mean(),
            "benchmark_return": grouped["benchmark_return"].mean(),
            "excess": grouped["excess"].mean(),
            "hit_rate": grouped["beat"].mean(),
        }
    ).reset_index()
    result["invested"] = result["positions"] * settings.position_usd
    result["wallet_return"] = result["value"] / result["invested"] - 1
    spread = result.pivot_table(
        index=["decision_date", "horizon_months", "end_date"],
        columns="side",
        values="stock_return",
    )
    if set(SIDES) <= set(spread.columns):
        long_short = (spread["buy"] - spread["sell"]).rename("excess").reset_index()
        result = pd.concat(
            [result, long_short.assign(side="long_short")], ignore_index=True
        )
    result["period"] = [
        settings.period(pd.Timestamp(d)) for d in result["decision_date"]
    ]
    columns = [
        "decision_date",
        "period",
        "horizon_months",
        "end_date",
        "side",
        "positions",
        "invested",
        "value",
        "benchmark_value",
        "stock_return",
        "wallet_return",
        "benchmark_return",
        "excess",
        "hit_rate",
    ]
    return result[columns].sort_values(keys, ignore_index=True)


def model_score(wallet_table: pd.DataFrame, settings: Evaluation) -> pd.DataFrame:
    """Return the annualised excess return of the chained buy wallet, per period.

    Parameters
    ----------
    wallet_table : pd.DataFrame
        ``wallets`` output.
    settings : Evaluation
        Score horizon and periods.

    Returns
    -------
    pd.DataFrame
        One row per period (``in-sample``, ``held-out``, ``all``): ``decisions``,
        ``first_decision``, ``last_end``, ``wallet_growth`` and ``benchmark_growth``
        (growth of 1 USD), ``annualised_excess`` (the model score, fraction per year)
        and ``mean_hit_rate``.

    Notes
    -----
    The buy wallet of each decision year is held for the score horizon (one year), so
    consecutive windows follow each other and their returns chain into one path. A
    decision year with no buy signal is left out of the chain.
    """
    buys = wallet_table[
        (wallet_table["side"] == "buy")
        & (wallet_table["horizon_months"] == settings.score_horizon_months)
    ]
    return chained_score(buys)


def chained_score(path: pd.DataFrame) -> pd.DataFrame:
    """Return the annualised excess of a yearly wallet chained over its decisions.

    Parameters
    ----------
    path : pd.DataFrame
        One row per decision: ``decision_date``, ``end_date``, ``period``,
        ``wallet_return``, ``benchmark_return``, ``hit_rate``; windows that follow each
        other (held one year, decided yearly).

    Returns
    -------
    pd.DataFrame
        As ``model_score``: one row per period (``in-sample``, ``held-out``, ``all``).
    """
    path = path.sort_values("decision_date")
    rows: list[dict[str, object]] = []
    for period in ("in-sample", "held-out", "all"):
        own = path if period == "all" else path[path["period"] == period]
        if own.empty:
            continue
        index = [own["decision_date"].iloc[0], *own["end_date"]]
        wallet = pd.Series([1.0, *(1 + own["wallet_return"]).cumprod()], index=index)
        market = pd.Series([1.0, *(1 + own["benchmark_return"]).cumprod()], index=index)
        rows.append(
            {
                "period": period,
                "decisions": len(own),
                "first_decision": index[0],
                "last_end": index[-1],
                "wallet_growth": float(wallet.iloc[-1]),
                "benchmark_growth": float(market.iloc[-1]),
                "annualised_excess": annualised_relative_return(
                    wallet, market, min_years=0.5
                ),
                "mean_hit_rate": float(own["hit_rate"].mean()),
            }
        )
    return pd.DataFrame(rows)


def correlation_curve(
    table: pd.DataFrame,
    prices: pd.DataFrame,
    dates: Sequence[pd.Timestamp],
    settings: Evaluation,
    *,
    benchmark: str,
) -> pd.DataFrame:
    """Return the rank correlation of score and forward excess return per horizon.

    Parameters
    ----------
    table : pd.DataFrame
        The buyability table (``symbol``, ``date``, ``score``).
    prices : pd.DataFrame
        Columns ``symbol``, ``date``, ``adj_close``, including ``benchmark``.
    dates : Sequence[pd.Timestamp]
        Rebalance dates the score is taken on.
    settings : Evaluation
        Longest horizon and periods.
    benchmark : str
        Total-return benchmark symbol; windows ending after its last price are left out.

    Returns
    -------
    pd.DataFrame
        Columns ``date``, ``period``, ``horizon_months``, ``ic`` (Spearman), ``companies``;
        dates with fewer than ``settings.min_companies`` companies are left out.
    """
    own = table[table["date"].isin(list(dates))].dropna(subset=["score"])
    index = pd.MultiIndex.from_arrays(
        [own["symbol"].astype("string"), own["date"]], names=["symbol", "date"]
    )
    scores = pd.Series(own["score"].to_numpy(), index=index)
    rows: list[dict[str, object]] = []
    for month in range(1, settings.correlation_max_months + 1):
        excess = window_returns(prices, index, benchmark=benchmark, months=month)
        for value, part in excess["excess"].groupby(level="date"):
            day = pd.Timestamp(str(value))
            both = pd.DataFrame(
                {
                    "score": scores.xs(day, level="date"),
                    "excess": part.droplevel("date"),
                }
            ).dropna()
            if len(both) < settings.min_companies:
                continue
            rows.append(
                {
                    "date": day,
                    "period": settings.period(day),
                    "horizon_months": month,
                    "ic": rank_correlation(both["score"], both["excess"]),
                    "companies": len(both),
                }
            )
    columns = ["date", "period", "horizon_months", "ic", "companies"]
    return (
        pd.DataFrame(rows, columns=columns)
        .sort_values(["date", "horizon_months"])
        .reset_index(drop=True)
    )


@dataclass(frozen=True)
class Wallet:
    """The settings of the ranked long-short wallet (``[wallet]`` in ``config/rules.toml``).

    Parameters
    ----------
    score_column : str
        The score ranked (``score`` or ``score_binned``).
    weighting : str
        ``score`` (weights in proportion to the score) or ``rank`` (``rank_weights``).
    names : int
        Companies per book: exactly this many (fewer when fewer are scored); a tie at the
        last place is broken by symbol.
    book_usd : float
        Money per book; the wallet trades twice this.
    horizon_months : int
        Holding period.
    rank_weights : tuple[float, ...]
        Weights by rank for ``rank``, highest first.
    """

    score_column: str
    weighting: str
    names: int
    book_usd: float
    horizon_months: int
    rank_weights: tuple[float, ...]

    @property
    def label(self) -> str:
        """Return a short model name, e.g. ``top 5, score_binned, score weights``."""
        return f"top {self.names}, {self.score_column}, {self.weighting} weights"


def book_weights(scores: pd.Series, wallet: Wallet, *, side: str) -> pd.Series:
    """Return the weights of the companies bought (``buy``) or sold (``sell``).

    Parameters
    ----------
    scores : pd.Series
        Score per company (index ``symbol``) on one date, without missing values.
    wallet : Wallet
        Book size and weighting.
    side : str
        ``buy`` takes the highest scores, ``sell`` the lowest.

    Returns
    -------
    pd.Series
        Weights summing to 1, indexed by symbol, in rank order: exactly ``wallet.names``
        companies (fewer when fewer are scored); a tie at the last place is broken by
        symbol, in alphabetical order.

    Raises
    ------
    ValueError
        When the weighting is ``rank`` and ``wallet.rank_weights`` has fewer entries than
        ``wallet.names``.
    """
    if wallet.weighting == "rank" and len(wallet.rank_weights) < wallet.names:
        raise ValueError(
            f"rank weighting needs {wallet.names} rank_weights, got "
            f"{len(wallet.rank_weights)}: ranks beyond them would get no money"
        )
    ordered = scores.sort_index().sort_values(ascending=side == "sell", kind="stable")
    chosen = ordered.iloc[: wallet.names]
    if wallet.weighting == "rank":
        base = np.zeros(len(chosen))
        given = np.asarray(wallet.rank_weights[: len(chosen)], dtype=float)
        base[: len(given)] = given
        # Tied companies share the mean weight of the ranks they span.
        ranks = pd.DataFrame({"score": chosen.to_numpy(), "base": base})
        shared = ranks.groupby("score")["base"].transform("mean")
        strength = pd.Series(shared.to_numpy(dtype=float), index=chosen.index)
    elif side == "buy":
        strength = chosen
    else:
        strength = pd.Series(1.0, index=chosen.index)
    if chosen.empty:
        return chosen.astype(float)
    total = float(strength.sum())
    if total <= 0:
        return pd.Series(1 / len(chosen), index=chosen.index)
    return strength / total


def ranked_positions(
    table: pd.DataFrame, dates: Sequence[pd.Timestamp], wallet: Wallet
) -> pd.DataFrame:
    """Return the ranked wallet's positions on each decision date.

    Parameters
    ----------
    table : pd.DataFrame
        The buyability table (``symbol``, ``date``, ``wallet.score_column``).
    dates : Sequence[pd.Timestamp]
        Decision dates; the latest rebalance date on or before each is used.
    wallet : Wallet
        Book size and weighting.

    Returns
    -------
    pd.DataFrame
        Columns ``decision_date``, ``score_date``, ``symbol``, ``score``, ``side``,
        ``weight`` (within the book) and ``amount`` (USD).
    """
    scored = sorted(pd.Timestamp(d) for d in table["date"].unique())
    frames: list[pd.DataFrame] = []
    for day in dates:
        known = [d for d in scored if d <= day]
        if not known:
            continue
        own = table.loc[table["date"] == known[-1]].dropna(subset=[wallet.score_column])
        scores = own.set_index("symbol")[wallet.score_column]
        for side in SIDES:
            weight = book_weights(scores, wallet, side=side)
            frames.append(
                pd.DataFrame(
                    {
                        "decision_date": day,
                        "score_date": known[-1],
                        "symbol": weight.index,
                        "score": scores.reindex(weight.index).to_numpy(),
                        "side": side,
                        "weight": weight.to_numpy(),
                        "amount": wallet.book_usd * weight.to_numpy(),
                    }
                )
            )
    return pd.concat(frames, ignore_index=True)


def ranking(
    table: pd.DataFrame,
    day: pd.Timestamp,
    *,
    by: str,
    columns: Sequence[str] = (),
) -> pd.DataFrame:
    """Return every scored company on the latest rebalance date, best to worst.

    Parameters
    ----------
    table : pd.DataFrame
        The buyability table (``symbol``, ``date`` and the columns named below).
    day : pd.Timestamp
        The latest rebalance date on or before it is used.
    by : str
        The column that ranks the companies, highest first (e.g. the 0-to-1 score).
    columns : Sequence[str]
        Further columns of the table to carry along.

    Returns
    -------
    pd.DataFrame
        ``rank`` (1 for the highest ``by``), ``symbol``, ``score_date``, ``by`` and
        ``columns``, in rank order; a tie is ordered by symbol. Companies without a
        value in ``by`` are left out. Empty when no rebalance date is known by ``day``.

    Notes
    -----
    The wallet's picks rank by its own score column, not by the 0-to-1 score, so the
    first rows of a ranking by ``by`` need not be the picks.
    """
    scored = sorted(pd.Timestamp(d) for d in table["date"].unique())
    known = [d for d in scored if d <= day]
    if not known:
        return pd.DataFrame(columns=["rank", "symbol", "score_date", by, *columns])
    latest = known[-1]
    own = table.loc[table["date"] == latest].dropna(subset=[by]).set_index("symbol")
    ordered = own[by].sort_index().sort_values(ascending=False, kind="stable")
    result = pd.DataFrame(
        {
            "rank": range(1, len(ordered) + 1),
            "symbol": ordered.index,
            "score_date": latest,
            by: ordered.to_numpy(),
        }
    )
    for column in columns:
        result[column] = own[column].reindex(ordered.index).to_numpy()
    return result


def ranked_wallet(
    positions: pd.DataFrame,
    prices: pd.DataFrame,
    wallet: Wallet,
    settings: Evaluation,
    *,
    benchmark: str,
) -> pd.DataFrame:
    """Return the ranked wallet's return and excess over the benchmark per decision.

    The wallet is the buy book; the sell book's excess and hit rate are reported beside
    it.

    Parameters
    ----------
    positions : pd.DataFrame
        ``ranked_positions`` output.
    prices : pd.DataFrame
        Columns ``symbol``, ``date``, ``adj_close``, including ``benchmark``.
    wallet : Wallet
        Holding period and book size.
    settings : Evaluation
        Periods.
    benchmark : str
        Total-return benchmark symbol; windows ending after its last price are left out.

    Returns
    -------
    pd.DataFrame
        One row per decision: ``decision_date``, ``end_date``, ``period``, ``positions``
        (bought), ``long_excess`` and ``short_excess`` (each book's excess per USD of
        the book), ``wallet_return`` (index plus ``long_excess``), ``benchmark_return``,
        ``excess`` (= ``long_excess``), ``hit_rate`` and ``short_hit_rate`` (share of
        each book's money in positions that beat the benchmark).

    Notes
    -----
    A position without prices over its window is dropped and its money left in the
    index, so it adds no excess.
    """
    end = pd.Timestamp(prices.loc[prices["symbol"] == benchmark, "date"].max())
    held = holdings(
        positions,
        prices,
        replace(settings, horizons_months=(wallet.horizon_months,)),
        benchmark=benchmark,
        end=end,
    )
    held = held.assign(
        contribution=held["amount"] * held["excess"] / wallet.book_usd,
        won=held["amount"] * held["beat"] / wallet.book_usd,
    )
    keys = ["decision_date", "end_date"]
    buys = held[held["side"] == "buy"].groupby(keys)
    sells = held[held["side"] == "sell"].groupby(keys)
    path = pd.DataFrame(
        {
            "positions": buys.size(),
            "long_excess": buys["contribution"].sum(),
            "short_excess": sells["contribution"].sum(),
            "benchmark_return": held.groupby(keys)["benchmark_return"].mean(),
            "hit_rate": buys["won"].sum(),
            "short_hit_rate": sells["won"].sum(),
        }
    ).reset_index()
    edges = ["long_excess", "short_excess"]
    path[edges] = path[edges].fillna(0.0)
    path["excess"] = path["long_excess"]
    path["wallet_return"] = path["benchmark_return"] + path["excess"]
    path["period"] = [settings.period(pd.Timestamp(d)) for d in path["decision_date"]]
    return path


def short_path(path: pd.DataFrame) -> pd.DataFrame:
    """Return a ranked wallet's sell book as a yearly path of its own.

    ``path`` is ``ranked_wallet`` output; the sell book's return is the index's plus
    its excess (``benchmark_return + short_excess``) and its hit rate the sell book's.
    """
    return path.assign(
        wallet_return=path["benchmark_return"] + path["short_excess"],
        hit_rate=path["short_hit_rate"],
    )
