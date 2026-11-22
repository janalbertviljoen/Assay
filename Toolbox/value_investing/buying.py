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
    """Return the ranked wallet of ``[wallet]``, ``[ledger]`` and ``[report]``."""
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

    Each with its ``gics_sector`` and its 0-to-1 score as ``score_share``; the lowest
    scores sorted by score.
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
    """Return the latest ``value`` of ``series_id`` on or before ``end``, with its date."""
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

    ``settings`` is ``[report.buy_list]``; the amounts are in its ``currency``, turned
    into USD at ``rate`` (units per USD). Prices after ``end`` are not used.
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
