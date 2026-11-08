"""
market_data/sources/prices.py
-----------------------------
Daily prices, dividends and splits from Yahoo Finance's chart endpoint.

The provider fetches one symbol's full daily history up to the as-of date through the
central ``ApiClient`` (the endpoint ``yfinance`` also uses); snapshots store the JSON as
received. The parser returns three tables: prices, dividends and splits. Daily bars give
the prices; monthly bars over a longer period give the dividend and split history at
little cost, which serves the 20-year dividend record (G4) where EDGAR, whose XBRL
filings start in 2009, cannot.

Yahoo adjusts its data as of the day it is fetched: ``close`` and dividend amounts are
adjusted for every split up to then, and ``adj_close`` is adjusted for splits and
dividends (a total-return series). The splits table allows a later stage to undo the
split adjustment, so prices can be compared with per-share figures as reported in
filings.

Owns
----
The Yahoo chart endpoint and headers, the symbol convention, and the price, dividend and
split source models, their columns and their table schemas.

Must not
--------
Undo split adjustments or compute returns (later stages); choose which prices a
rebalance uses (point-in-time stage).

Public API
----------
yahoo_client(*, max_requests_per_second, ...)
    An ``ApiClient`` with the headers Yahoo accepts.
YahooChart(client, start, interval)
    The ``DataProvider`` for the chart endpoint; the query is a ticker.
parse_chart(content)
    Raw JSON to ``ChartTables(prices, dividends, splits)``.
load_chart(tickers, *, provider, store, as_of)
    Snapshot and parse several symbols into one ``ChartTables``.
yahoo_symbol(ticker)
    A ticker in Yahoo's convention (``BRK.B`` to ``BRK-B``).
PRICE_SCHEMA, DIVIDEND_SCHEMA, SPLIT_SCHEMA
    The schemas of the three tables, checked where they are written and read.
PRICE_CURRENCY
    The one currency the price tables may hold (USD).
LISTING_COLUMNS, LISTING_SCHEMA
    The columns and schema of the listings table, built from the monthly bars.

Dependency rule
---------------
pandas, the standard library, ``skatkis.io`` and ``skatkis.pipelines``.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from urllib.parse import quote

import pandas as pd

from Toolbox.skatkis.io.api import ApiClient
from Toolbox.skatkis.io.provider import DataProvider, RawPayload
from Toolbox.skatkis.io.snapshots import SnapshotStore, fetch_snapshot
from Toolbox.skatkis.pipelines.contracts import Schema
from Toolbox.skatkis.pipelines.schema import (
    allowed_values,
    from_dtypes,
    identifier,
    non_negative,
    positive,
    required,
    unique_key,
)

CHART_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
USER_AGENT = "Mozilla/5.0 (compatible; trading-bot research)"

PRICE_COLUMNS: dict[str, str] = {
    "symbol": "string",
    "date": "datetime64[ns]",
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "adj_close": "float64",
    "volume": "float64",
    "currency": "string",
}
"""Daily prices in ``currency`` per share; ``close`` split-adjusted, ``adj_close`` split-
and dividend-adjusted, both as of the snapshot date. Days without a trade keep their row
with missing values."""

DIVIDEND_COLUMNS: dict[str, str] = {
    "symbol": "string",
    "ex_date": "datetime64[ns]",
    "amount": "float64",
    "currency": "string",
}
"""Cash dividends per share on their ex-dividend date, split-adjusted as of the snapshot
date."""

SPLIT_COLUMNS: dict[str, str] = {
    "symbol": "string",
    "date": "datetime64[ns]",
    "numerator": "float64",
    "denominator": "float64",
}
"""Splits on their effective date: ``numerator`` new shares for ``denominator`` old."""

PRICE_CURRENCY = "USD"
"""The one currency the price tables may hold; every later stage reads prices as USD."""

PRICE_SCHEMA: Schema = from_dtypes(
    PRICE_COLUMNS,
    {
        "symbol": identifier | required | unique_key,
        "date": required | unique_key,
        "open": positive,
        "high": positive,
        "low": positive,
        "close": positive,
        "adj_close": positive,
        "volume": non_negative,
        "currency": required | allowed_values({PRICE_CURRENCY}),
    },
)
"""The prices table: one row per symbol and day; a day without a trade has missing
prices but never a price of 0 or below."""

DIVIDEND_SCHEMA: Schema = from_dtypes(
    DIVIDEND_COLUMNS,
    {
        "symbol": identifier | required | unique_key,
        "ex_date": required | unique_key,
        "amount": required | positive,
        "currency": required | allowed_values({PRICE_CURRENCY}),
    },
)
"""The dividends table: one cash dividend per symbol and ex-dividend date."""

SPLIT_SCHEMA: Schema = from_dtypes(
    SPLIT_COLUMNS,
    {
        "symbol": identifier | required | unique_key,
        "date": required | unique_key,
        "numerator": required | positive,
        "denominator": required | positive,
    },
)
"""The splits table: one split per symbol and date; a ratio part of 0 would corrupt every
split factor after it."""

LISTING_COLUMNS: dict[str, str] = {"symbol": "string", "first_date": "datetime64[ns]"}
"""Each symbol's first monthly bar, no earlier than the monthly provider's start; built
by the update from the monthly bars."""

LISTING_SCHEMA: Schema = from_dtypes(
    LISTING_COLUMNS,
    {"symbol": identifier | required | unique_key, "first_date": required},
)
"""The listings table: one row per symbol."""


class PriceParseError(ValueError):
    """A chart payload is malformed or reports an error for its symbol."""


@dataclass(frozen=True)
class ChartTables:
    """The three tables parsed from chart payloads."""

    prices: pd.DataFrame
    dividends: pd.DataFrame
    splits: pd.DataFrame


def yahoo_symbol(ticker: str) -> str:
    """Return ``ticker`` in Yahoo's convention: upper case, ``.`` replaced by ``-``."""
    return ticker.strip().upper().replace(".", "-")


def yahoo_client(
    *,
    max_requests_per_second: float,
    timeout_seconds: float,
    max_retries: int,
    backoff_seconds: float,
) -> ApiClient:
    """Return an ``ApiClient`` that sends a User-Agent Yahoo accepts.

    Parameters come from ``config/market_data.toml`` (``[sources.yahoo]``).
    """
    return ApiClient(
        headers={"User-Agent": USER_AGENT},
        max_requests_per_second=max_requests_per_second,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        backoff_seconds=backoff_seconds,
    )


@dataclass(frozen=True)
class YahooChart(DataProvider):
    """``DataProvider`` for the Yahoo chart endpoint; the query is a ticker.

    Parameters
    ----------
    client : ApiClient
        Normally from ``yahoo_client``.
    start : date
        First day requested.
    interval : str
        Bar length: ``"1d"`` for daily prices, ``"1mo"`` for a long history of
        dividends and splits at little cost (events keep their own dates).

    Notes
    -----
    A snapshot is keyed by source name, ticker and as-of date, so a changed ``start``
    with the same as-of date reuses the stored snapshot; take a new as-of date instead.
    """

    client: ApiClient
    start: date
    interval: str = "1d"
    url_template: str = CHART_URL

    @property
    def name(self) -> str:
        """Snapshot folder name: ``yahoo_<interval>``, e.g. ``yahoo_1d``."""
        return f"yahoo_{self.interval}"

    def fetch(self, query: str, as_of: date) -> RawPayload:
        """Return the chart JSON for ticker ``query`` from ``start`` to ``as_of``.

        Both ends are inclusive; ``as_of`` fixes the request, so the same snapshot date
        always asks for the same range.
        """
        url = self.url_template.format(symbol=quote(yahoo_symbol(query), safe=""))
        params = {
            "period1": str(_epoch(self.start)),
            "period2": str(_epoch(as_of + timedelta(days=1))),
            "interval": self.interval,
            "events": "div,split",
            "includeAdjustedClose": "true",
        }
        return RawPayload(content=self.client.get(url, params), extension="json")


def parse_chart(content: bytes) -> ChartTables:
    """Return the prices, dividends and splits in one chart payload.

    Parameters
    ----------
    content : bytes
        The chart JSON as received.

    Returns
    -------
    ChartTables
        Tables with the columns of ``PRICE_COLUMNS``, ``DIVIDEND_COLUMNS`` and
        ``SPLIT_COLUMNS``, sorted by date.

    Raises
    ------
    PriceParseError
        If the payload is not chart JSON, reports an error, or lacks the timestamps,
        quotes or adjusted closes. The message names the symbol where known.

    Notes
    -----
    A timestamp is converted to a trading date with the exchange's UTC offset from the
    payload. That offset is the current one (daylight saving may differ), which never
    moves a regular-session timestamp to another date.
    """
    try:
        document = json.loads(content)
    except json.JSONDecodeError as error:
        raise PriceParseError(f"chart payload is not valid JSON: {error}") from error
    chart = cast(dict[str, Any], cast(dict[str, Any], document).get("chart", {}))
    if chart.get("error"):
        raise PriceParseError(f"chart payload reports an error: {chart['error']}")
    results = cast(list[dict[str, Any]], chart.get("result") or [])
    if not results:
        raise PriceParseError("chart payload has no result")
    result = results[0]
    meta = cast(dict[str, Any], result["meta"])
    symbol = str(meta["symbol"])
    currency = str(meta.get("currency", ""))
    offset = int(meta.get("gmtoffset", 0))
    try:
        timestamps = cast(list[int], result["timestamp"])
        indicators = cast(
            dict[str, list[dict[str, list[float | None]]]], result["indicators"]
        )
        quote_ = indicators["quote"][0]
        adj_close = indicators["adjclose"][0]["adjclose"]
    except (KeyError, IndexError) as error:
        raise PriceParseError(f"{symbol}: chart payload lacks {error}") from error

    prices = pd.DataFrame(
        {
            "symbol": symbol,
            "date": _dates(timestamps, offset),
            "open": quote_["open"],
            "high": quote_["high"],
            "low": quote_["low"],
            "close": quote_["close"],
            "adj_close": adj_close,
            "volume": quote_["volume"],
            "currency": currency,
        }
    )
    events = cast(dict[str, dict[str, dict[str, Any]]], result.get("events", {}))
    dividends_raw = list(events.get("dividends", {}).values())
    splits_raw = list(events.get("splits", {}).values())
    dividends = pd.DataFrame(
        {
            "symbol": symbol,
            "ex_date": _dates([int(e["date"]) for e in dividends_raw], offset),
            "amount": [float(e["amount"]) for e in dividends_raw],
            "currency": currency,
        }
    )
    splits = pd.DataFrame(
        {
            "symbol": symbol,
            "date": _dates([int(e["date"]) for e in splits_raw], offset),
            "numerator": [float(e["numerator"]) for e in splits_raw],
            "denominator": [float(e["denominator"]) for e in splits_raw],
        }
    )
    return ChartTables(
        prices=_typed(prices, PRICE_COLUMNS, "date"),
        dividends=_typed(dividends, DIVIDEND_COLUMNS, "ex_date"),
        splits=_typed(splits, SPLIT_COLUMNS, "date"),
    )


def load_chart(
    tickers: Sequence[str], *, provider: DataProvider, store: SnapshotStore, as_of: date
) -> ChartTables:
    """Snapshot (if not stored yet) and parse the chart of each ticker.

    Returns
    -------
    ChartTables
        The tables of ``parse_chart`` for every ticker, in the order given.
    """
    parsed = [
        parse_chart(fetch_snapshot(provider, yahoo_symbol(ticker), as_of, store))
        for ticker in tickers
    ]
    empty = _empty_tables()
    return ChartTables(
        prices=_concat([t.prices for t in parsed], empty.prices),
        dividends=_concat([t.dividends for t in parsed], empty.dividends),
        splits=_concat([t.splits for t in parsed], empty.splits),
    )


def _empty_tables() -> ChartTables:
    """Return empty tables with the chart columns and dtypes."""
    return ChartTables(
        prices=_typed(pd.DataFrame(columns=list(PRICE_COLUMNS)), PRICE_COLUMNS, "date"),
        dividends=_typed(
            pd.DataFrame(columns=list(DIVIDEND_COLUMNS)), DIVIDEND_COLUMNS, "ex_date"
        ),
        splits=_typed(pd.DataFrame(columns=list(SPLIT_COLUMNS)), SPLIT_COLUMNS, "date"),
    )


def _epoch(day: date) -> int:
    """Return midnight UTC of ``day`` in seconds since 1970-01-01."""
    return int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp())


def _dates(timestamps: Sequence[int], offset: int) -> pd.Series:
    """Return the exchange-local trading dates of UTC ``timestamps``."""
    seconds = pd.Series(timestamps, dtype="int64") + offset
    return pd.to_datetime(seconds, unit="s").dt.normalize()


def _typed(frame: pd.DataFrame, columns: dict[str, str], sort_by: str) -> pd.DataFrame:
    """Cast ``frame`` to ``columns`` and sort it stably by ``sort_by``."""
    typed = frame[list(columns)].astype(columns)
    return typed.sort_values([sort_by], kind="stable").reset_index(drop=True)


def _concat(frames: list[pd.DataFrame], empty: pd.DataFrame) -> pd.DataFrame:
    """Concatenate ``frames``, or return ``empty`` when there are none."""
    return pd.concat(frames, ignore_index=True) if frames else empty
