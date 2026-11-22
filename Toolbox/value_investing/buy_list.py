"""
value_investing/buy_list.py
---------------------------
The personal buy list: the next picks bought with a sum of money under four weightings,
companies the investor buys outside the model, and where each price stands in its trend.

The next picks come from ``value_investing.evaluation``; this module turns them into
money (in the investor's currency, turned into USD at the latest rate) and fractional
shares at the latest close, by score (the model's weights), by rank
in equal steps, by dip (the same steps, the lowest price in its range first) and a blend
of rank and dip, and adds the fixed purchases the investor chose. Nothing here enters the
wallets or the backtest: the fixed companies are the investor's choice, made today.

Owns
----
The rank-ramp weights, the buy list and the trend state of each company in it.

Must not
--------
Choose or score companies (``value_investing.evaluation``, ``value_investing.scoring``);
compute the trend measures (``skatkis.financial_logic.price_trend``); plot or save.

Public API
----------
ramp_weights(count, *, first, last)
    Weights falling in equal steps from ``first`` to ``last``, summing to 1.
buy_list(picks, closes, in_range, *, rate, picks_amount, ramp, blend, fixed)
    Money and shares per company by score, rank, dip and blend, and the fixed purchases.
price_trends(prices, symbols, *, trend_days, smooth_days, high_days, range_days)
    The trend measures of each company's price over time.
trend_states(trends, *, lag_days)
    Each company's latest trend measures and the state read from them.

Computes
--------
rank-ramp weight, linear rank weight : ramp_weights
    w_k = a_k / Σ a_j with a_k = first + (last - first) (k - 1) / (n - 1) for ranks
    k = 1..n; one company gets 1.
blended rank and dip weight : buy_list
    w = (b_r w_rank + b_d w_dip) / (b_r + b_d), with (b_r, b_d) = ``blend``.

Dependency rule
---------------
pandas, the standard library and ``skatkis.financial_logic``.
"""

import math
from collections.abc import Mapping, Sequence

import pandas as pd

from Toolbox.skatkis.financial_logic import price_trend

MODEL = "model"
OWN = "own choice"
WEIGHTINGS = ("score", "rank", "dip", "blend")


def ramp_weights(count: int, *, first: float, last: float) -> list[float]:
    """Return ``count`` weights falling in equal steps from ``first`` to ``last``.

    The weights are scaled to sum to 1, so only the ratio of ``first`` to ``last``
    matters: 3 to 1 over 10 companies gives 15% down to 5%.
    """
    if count == 1:
        return [1.0]
    raw = [first + (last - first) * k / (count - 1) for k in range(count)]
    total = sum(raw)
    return [r / total for r in raw]


def buy_list(  # noqa: PLR0913  one keyword per amount and weighting setting
    picks: pd.DataFrame,
    closes: pd.Series,
    in_range: pd.Series,
    *,
    rate: float,
    picks_amount: float,
    ramp: tuple[float, float],
    blend: tuple[float, float],
    fixed: Mapping[str, float],
) -> pd.DataFrame:
    """Return the purchases: the picks by score, rank, dip and blend, then the fixed ones.

    Parameters
    ----------
    picks : pd.DataFrame
        The next picks: ``symbol``, ``score`` and ``weight`` (the model's weight by
        score, summing to 1).
    closes : pd.Series
        The latest close (USD) per symbol.
    in_range : pd.Series
        The latest place of each price in its range per symbol, 0 at the low and 1 at
        the high (``skatkis.financial_logic.price_trend``).
    rate : float
        Units of the investor's currency per USD (1 when it is USD).
    picks_amount : float
        Money spread over the picks, in the investor's currency.
    ramp : tuple[float, float]
        The first and last step (``ramp_weights``) of the rank and dip weightings.
    blend : tuple[float, float]
        The parts of rank and of dip in the blended weighting (2 and 1: two thirds rank).
    fixed : Mapping[str, float]
        Money per company bought outside the model, in the investor's currency, the
        same under every weighting.

    Returns
    -------
    pd.DataFrame
        One row per company, picks first (highest score first), then the fixed ones:
        ``symbol``, ``choice`` (``model`` or ``own choice``), ``score`` (missing for
        the fixed), ``close`` (USD), ``in_range``, and per weighting ``score_``,
        ``rank_``, ``dip_`` and ``blend_``: ``weight`` (of all the money), ``amount`` (investor's
        currency), ``usd`` = amount / rate and ``shares`` = usd / close, fractional.

    Notes
    -----
    The dip weighting gives the rank weighting's steps in the order of ``in_range``,
    lowest first; a tie, or a company without a range, goes by score, and one without
    a range comes last.
    """
    ordered = picks.sort_values(["score", "symbol"], ascending=[False, True])
    total = picks_amount + sum(fixed.values())
    steps = ramp_weights(len(ordered), first=ramp[0], last=ramp[1])
    by_dip = ordered.assign(in_range=ordered["symbol"].map(in_range)).sort_values(
        "in_range", kind="stable", na_position="last"
    )
    dip_steps = dict(zip(by_dip["symbol"], steps, strict=True))
    rows: list[dict[str, object]] = []
    for row, step in zip(ordered.to_dict("records"), steps, strict=True):
        rows.append(
            {
                "symbol": row["symbol"],
                "choice": MODEL,
                "score": float(row["score"]),
                "score_amount": picks_amount * float(row["weight"]),
                "rank_amount": picks_amount * step,
                "dip_amount": picks_amount * dip_steps[row["symbol"]],
                "blend_amount": picks_amount
                * (blend[0] * step + blend[1] * dip_steps[row["symbol"]])
                / (blend[0] + blend[1]),
            }
        )
    for symbol, amount in fixed.items():
        rows.append(
            {
                "symbol": symbol,
                "choice": OWN,
                "score": math.nan,
                "score_amount": float(amount),
                "rank_amount": float(amount),
                "dip_amount": float(amount),
                "blend_amount": float(amount),
            }
        )
    table = pd.DataFrame(rows)
    table["close"] = table["symbol"].map(closes).astype(float)
    table["in_range"] = table["symbol"].map(in_range).astype(float)
    for weighting in WEIGHTINGS:
        amount = table[f"{weighting}_amount"]
        table[f"{weighting}_weight"] = amount / total
        table[f"{weighting}_usd"] = amount / rate
        table[f"{weighting}_shares"] = table[f"{weighting}_usd"] / table["close"]
    columns = ["symbol", "choice", "score", "close", "in_range"]
    for weighting in WEIGHTINGS:
        columns += [
            f"{weighting}_weight",
            f"{weighting}_amount",
            f"{weighting}_usd",
            f"{weighting}_shares",
        ]
    return table[columns]


def price_trends(  # noqa: PLR0913  one keyword per trend window
    prices: pd.DataFrame,
    symbols: Sequence[str],
    *,
    trend_days: int,
    smooth_days: int,
    high_days: int,
    range_days: int,
) -> pd.DataFrame:
    """Return the trend measures of each company's ``close`` over time.

    ``prices`` has ``symbol``, ``date`` and ``close``; the result has ``symbol``,
    ``date`` and the columns of ``skatkis.financial_logic.price_trend``.
    """
    parts: list[pd.DataFrame] = []
    for symbol in symbols:
        own = prices[prices["symbol"] == symbol].sort_values("date")
        trend = price_trend(
            own.set_index("date")["close"].dropna(),
            trend_days=trend_days,
            smooth_days=smooth_days,
            high_days=high_days,
            range_days=range_days,
        )
        parts.append(trend.reset_index().assign(symbol=symbol))
    return pd.concat(parts, ignore_index=True)


def trend_states(trends: pd.DataFrame, *, lag_days: int) -> pd.DataFrame:
    """Return each company's latest trend measures and the state read from them.

    Parameters
    ----------
    trends : pd.DataFrame
        ``price_trends`` output.
    lag_days : int
        Trading days back for the earlier slope.

    Returns
    -------
    pd.DataFrame
        Per symbol, in the order first seen: ``date``, ``price``, ``from_high``,
        ``from_trend``, ``in_range``, ``slope``, ``slope_before`` (``lag_days`` earlier) and
        ``state``: ``falling`` (slope below 0 and lower than before), ``falling,
        slowing`` (below 0 but higher than before), ``turning up below trend`` (slope
        at or above 0, price below its trend mean) or ``rising above trend``.
    """
    rows: list[dict[str, object]] = []
    for symbol, part in trends.groupby("symbol", sort=False):
        own = part.sort_values("date")
        last = own.iloc[-1]
        before = float(own["slope"].iloc[-1 - lag_days])
        slope = float(last["slope"])
        if slope < 0:
            state = "falling" if slope < before else "falling, slowing"
        elif float(last["from_trend"]) < 0:
            state = "turning up below trend"
        else:
            state = "rising above trend"
        rows.append(
            {
                "symbol": symbol,
                "date": last["date"],
                "price": float(last["price"]),
                "from_high": float(last["from_high"]),
                "from_trend": float(last["from_trend"]),
                "in_range": float(last["in_range"]),
                "slope": slope,
                "slope_before": before,
                "state": state,
            }
        )
    return pd.DataFrame(rows)
