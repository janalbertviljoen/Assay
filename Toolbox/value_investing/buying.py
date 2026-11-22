"""
value_investing/buying.py
-------------------------
The steps from the scored table to a buying decision, without IO: the report's wallet,
the next picks, the earlier trades of one investor, the exchange rate and the buy list.

``value_investing.__main__`` (the ``report`` and ``buy`` commands) and other tools that
show the picks (``steward``) call these with tables they have read; nothing is read,
written or plotted here.

Owns
----
The assembly of the next picks and the buy list from the stored tables and the
``[report]`` settings.

Must not
--------
Score or rank (``value_investing.evaluation``); hold or sell
(``value_investing.holding``); compute the buy list or the trends
(``value_investing.buy_list``); read, write or plot.

Public API
----------
report_wallet(rules)
    The ranked wallet the report and the buy list use.
next_picks(table, end, model, share_column)
    The next picks and the lowest scores on ``end``.
earlier_trades(table, prices, rules, model, *, end, benchmark)
    The trades of the investor the report follows (``pick_scenario``).
latest_rate(rates, series_id, end)
    The latest value of an exchange-rate series on or before ``end``, and its date.
prepare_buy_list(prices, picks, end, settings, rate)
    The buy list, each company's trend state and the trend series.

Dependency rule
---------------
pandas and ``value_investing.evaluation``, ``holding`` and ``buy_list``.
"""

from collections.abc import Mapping
from typing import Any

import pandas as pd

from Toolbox.value_investing import buy_list, evaluation, holding


def report_wallet(rules: Mapping[str, Any]) -> evaluation.Wallet:
    """Return the ranked wallet the report, the buy list and ``steward`` share.

    Parameters
    ----------
    rules : Mapping[str, Any]
        ``config/rules.toml``: ``[ledger] score_column``, ``[wallet] names``,
        ``horizon_months`` and ``rank_weights``, and ``[report] amount_usd``.

    Returns
    -------
    evaluation.Wallet
        Always weighted by score (``weighting="score"``): each pick's weight is its
        score over the sum of the picks' scores (``evaluation.book_weights``), with a
        book of ``amount_usd`` (USD).

    Raises
    ------
    KeyError
        When one of the settings above is missing.
    """
    return evaluation.Wallet(
        score_column=str(rules["ledger"]["score_column"]),
        weighting="score",
        names=int(rules["wallet"]["names"]),
        book_usd=float(rules["report"]["amount_usd"]),
        horizon_months=int(rules["wallet"]["horizon_months"]),
        rank_weights=tuple(float(w) for w in rules["wallet"]["rank_weights"]),
    )


def next_picks(
    table: pd.DataFrame, end: pd.Timestamp, model: evaluation.Wallet, share_column: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return the next picks and the lowest scores on ``end``.

    Parameters
    ----------
    table : pd.DataFrame
        The buyability table: ``symbol``, ``date``, ``gics_sector``, ``share_column``
        and ``model.score_column``.
    end : pd.Timestamp
        The decision date; the latest score date on or before it is used.
    model : evaluation.Wallet
        Book size and weighting (``report_wallet``).
    share_column : str
        The column of the 0-to-1 score shown beside the score.

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame]
        The picks (``side == "buy"``, in the order of ``evaluation.ranked_positions``:
        highest score first) and the lowest scores (``side == "sell"``, sorted by
        ``score`` then ``symbol``, lowest first). Each has the columns of
        ``evaluation.ranked_positions`` (``decision_date``, ``score_date``,
        ``symbol``, ``score``, ``side``, ``weight``, ``amount`` in USD) plus ``date``,
        ``gics_sector`` and ``score_share``.

    Raises
    ------
    ValueError
        When no score date lies on or before ``end`` (``evaluation.ranked_positions``
        has nothing to concatenate).
    """
    now = evaluation.ranked_positions(table, [end], model)
    now = now.merge(
        table[["symbol", "date", "gics_sector", share_column]],
        left_on=["symbol", "score_date"],
        right_on=["symbol", "date"],
    ).rename(columns={share_column: "score_share"})
    upcoming = now[now["side"] == "buy"]
    worst = now[now["side"] == "sell"].sort_values(["score", "symbol"])
    return upcoming, worst


def earlier_trades(  # noqa: PLR0913  one argument per input of the wallet
    table: pd.DataFrame,
    prices: pd.DataFrame,
    rules: Mapping[str, Any],
    model: evaluation.Wallet,
    *,
    end: pd.Timestamp,
    benchmark: str,
) -> pd.DataFrame:
    """Return the trades of the wallet with sells for the investor of ``pick_scenario``.

    The same wallet as the report's (``holding.buy_and_sell`` on the ranked picks of
    each decision date, on the benchmark's trading days, since the first start year),
    so the price charts mark the same earlier buys and sales.

    Parameters
    ----------
    table : pd.DataFrame
        The buyability table (``symbol``, ``date``, ``gics_sector``, the score and
        share columns).
    prices : pd.DataFrame
        Daily prices (``symbol``, ``date`` and the price columns ``holding`` reads).
    rules : Mapping[str, Any]
        ``config/rules.toml``; reads ``[report]`` ``start_years``,
        ``decision_months``, ``share_column``, ``sell_threshold``, ``amount_usd`` and
        ``pick_scenario``.
    model : evaluation.Wallet
        The ranked wallet (``report_wallet``).
    end : pd.Timestamp
        The last date of the holding period.
    benchmark : str
        The price symbol whose trading days give the decision dates.

    Returns
    -------
    pd.DataFrame
        ``holding.buy_and_sell(...).trades`` with ``scenario`` equal to
        ``pick_scenario`` (the start year); empty when no trade has that scenario.
    """
    settings = rules["report"]
    start_years = [int(y) for y in settings["start_years"]]
    days = prices[prices["symbol"] == benchmark]["date"]
    decisions = evaluation.decision_dates(
        [pd.Timestamp(d) for d in days],
        first_year=min(start_years),
        months=[int(m) for m in settings["decision_months"]],
    )
    positions = evaluation.ranked_positions(table, decisions, model).merge(
        table[["symbol", "gics_sector"]].drop_duplicates("symbol"), on="symbol"
    )
    shares = table.set_index(["symbol", "date"])[str(settings["share_column"])]
    managed = holding.buy_and_sell(
        positions,
        shares,
        prices,
        threshold=float(settings["sell_threshold"]),
        amount_usd=float(settings["amount_usd"]),
        start_years=start_years,
        end=end,
    )
    trades = managed.trades
    return trades[trades["scenario"] == int(settings["pick_scenario"])]


def latest_rate(
    rates: pd.DataFrame, series_id: str, end: pd.Timestamp
) -> tuple[float, pd.Timestamp]:
    """Return the latest ``value`` of ``series_id`` on or before ``end``, with its date.

    Parameters
    ----------
    rates : pd.DataFrame
        FRED observations: ``series_id``, ``date`` and ``value``.
    series_id : str
        The series, e.g. ``DEXSFUS`` (rand per USD).
    end : pd.Timestamp
        The last date that may be used; later observations are ignored.

    Returns
    -------
    tuple[float, pd.Timestamp]
        The value (units of the series) and its date. Missing values are skipped, so
        the date may lie before ``end``.

    Raises
    ------
    IndexError
        When ``series_id`` has no value on or before ``end``.
    """
    mask = (rates["series_id"] == series_id) & (rates["date"] <= end)
    series: pd.DataFrame = rates.loc[mask & rates["value"].notna()].sort_values("date")
    return float(series["value"].iloc[-1]), pd.Timestamp(series["date"].iloc[-1])


def prepare_buy_list(
    prices: pd.DataFrame,
    picks: pd.DataFrame,
    end: pd.Timestamp,
    settings: Mapping[str, Any],
    rate: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return the buy list, each company's trend state and the trend series.

    Parameters
    ----------
    prices : pd.DataFrame
        Daily prices: ``symbol``, ``date`` and ``close`` (USD, split-adjusted,
        dividends excluded). Prices after ``end`` are not used.
    picks : pd.DataFrame
        The next picks (``next_picks``): ``symbol``, ``score`` and ``weight``.
    end : pd.Timestamp
        The decision date.
    settings : Mapping[str, Any]
        ``[report.buy_list]`` with the investor's amounts: ``picks_amount`` and
        ``fixed`` (money per company outside the model) in its ``currency``,
        ``rank_ramp``, ``blend``, and the trend windows ``trend_days``,
        ``smooth_days``, ``high_days``, ``range_days`` and ``lag_days`` (trading days).
    rate : float
        Units of the investor's currency per USD (1 for USD).

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]
        ``buy_list.buy_list`` (the purchases under each weighting, the picks then the
        fixed companies), ``buy_list.trend_states`` (each company's latest measures
        and state) and ``buy_list.price_trends`` (the measures over time), for the
        picks and the fixed companies.

    Raises
    ------
    IndexError
        When a company has some, but fewer than ``lag_days + 1``, positive closes up
        to ``end`` (``buy_list.trend_states``). A company with no close at all is left
        out of the states and gets no ``in_range`` or shares in the list.

    Notes
    -----
    The close used to turn USD into shares is each company's last ``close`` on or
    before ``end``. The fixed purchases enter the list only; they are never part of
    the model's wallets.
    """
    fixed = {str(s): float(amount) for s, amount in settings["fixed"].items()}
    symbols = [*(str(s) for s in picks["symbol"]), *fixed]
    known = prices[prices["date"] <= end]
    closes = known.sort_values("date").groupby("symbol")["close"].last()
    trends = buy_list.price_trends(
        known,
        symbols,
        trend_days=int(settings["trend_days"]),
        smooth_days=int(settings["smooth_days"]),
        high_days=int(settings["high_days"]),
        range_days=int(settings["range_days"]),
    )
    states = buy_list.trend_states(trends, lag_days=int(settings["lag_days"]))
    orders = buy_list.buy_list(
        picks,
        closes,
        states.set_index("symbol")["in_range"],
        rate=rate,
        picks_amount=float(settings["picks_amount"]),
        ramp=(float(settings["rank_ramp"][0]), float(settings["rank_ramp"][1])),
        blend=(float(settings["blend"][0]), float(settings["blend"][1])),
        fixed=fixed,
    )
    return orders, states, trends
