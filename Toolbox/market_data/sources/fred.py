"""
market_data/sources/fred.py
---------------------------
Daily economic series from FRED (Federal Reserve Bank of St. Louis), such as exchange rates.

The tool uses ``DEXSFUS``: South African rand per US dollar, the Federal Reserve's H.10
noon buying rates in New York, daily from 1980. These rates are not revised after
publication, so the series as fetched is the series as it was known.

The provider fetches one series through the central ``ApiClient``. With an API key it
uses the official API (JSON); without one, the CSV download behind FRED's charts.
Snapshots store either as received, and the parser reads both into one table.

Owns
----
The FRED endpoints, the observation source model and its columns.

Must not
--------
Convert amounts between currencies (wallet and reporting); read the API key from the
environment (the command-line boundary).

Public API
----------
fred_client(*, max_requests_per_second, ...)
    An ``ApiClient`` for FRED.
FredSeries(client, start, api_key)
    The ``DataProvider`` for one series; the query is a series ID.
parse_fred(content, series_id)
    Raw JSON or CSV to one row per observation.
load_fred(series_ids, *, provider, store, as_of)
    Snapshot and parse several series into one table.
OBSERVATION_SCHEMA
    The schema of the observations table.

Dependency rule
---------------
pandas, the standard library, ``skatkis.io`` and ``skatkis.pipelines``.
"""

import io
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, cast

import pandas as pd

from Toolbox.skatkis.io.api import ApiClient
from Toolbox.skatkis.io.provider import DataProvider, RawPayload
from Toolbox.skatkis.io.snapshots import SnapshotStore, fetch_snapshot
from Toolbox.skatkis.pipelines.contracts import Schema
from Toolbox.skatkis.pipelines.schema import (
    from_dtypes,
    identifier,
    required,
    unique_key,
)

API_URL = "https://api.stlouisfed.org/fred/series/observations"
CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
USER_AGENT = "Mozilla/5.0 (compatible; trading-bot research)"
MISSING = {"", "."}

OBSERVATION_COLUMNS: dict[str, str] = {
    "series_id": "string",
    "date": "datetime64[ns]",
    "value": "float64",
}
"""One observation per day in the series' own unit (``DEXSFUS``: ZAR per USD). Days
without a published value (holidays) keep their row with a missing value."""

OBSERVATION_SCHEMA: Schema = from_dtypes(
    OBSERVATION_COLUMNS,
    {
        "series_id": identifier | required | unique_key,
        "date": required | unique_key,
    },
)
"""The observations table: one row per series and day; the value is in the series' own
unit and sign, so it carries no bound."""


class FredParseError(ValueError):
    """A FRED payload is malformed or lacks the requested series."""


def fred_client(
    *,
    max_requests_per_second: float,
    timeout_seconds: float,
    max_retries: int,
    backoff_seconds: float,
) -> ApiClient:
    """Return an ``ApiClient`` for FRED; the API key travels as a redacted parameter.

    Parameters come from ``config/market_data.toml`` (``[sources.fred]``).
    """
    return ApiClient(
        headers={"User-Agent": USER_AGENT},
        max_requests_per_second=max_requests_per_second,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        backoff_seconds=backoff_seconds,
    )


@dataclass(frozen=True)
class FredSeries(DataProvider):
    """``DataProvider`` for one FRED series; the query is a series ID (``DEXSFUS``).

    Parameters
    ----------
    client : ApiClient
        Normally from ``fred_client``.
    start : date
        First day requested.
    api_key : str or None
        FRED API key, read from the environment by the caller. With a key the official
        API is used, without one the chart CSV download. Never stored or shown.
    """

    client: ApiClient
    start: date
    api_key: str | None = field(default=None, repr=False)

    @property
    def name(self) -> str:
        """Snapshot folder name: ``fred``."""
        return "fred"

    def fetch(self, query: str, as_of: date) -> RawPayload:
        """Return the observations of series ``query`` from ``start`` to ``as_of``."""
        if self.api_key:
            params = {
                "series_id": query,
                "api_key": self.api_key,
                "file_type": "json",
                "observation_start": self.start.isoformat(),
                "observation_end": as_of.isoformat(),
            }
            return RawPayload(
                content=self.client.get(API_URL, params), extension="json"
            )
        params = {
            "id": query,
            "cosd": self.start.isoformat(),
            "coed": as_of.isoformat(),
        }
        return RawPayload(content=self.client.get(CSV_URL, params), extension="csv")


def parse_fred(content: bytes, series_id: str) -> pd.DataFrame:
    """Return the observations in a FRED payload, from either the API or the CSV download.

    Parameters
    ----------
    content : bytes
        API JSON (``{"observations": [...]}``) or chart CSV (a date column and a column
        named after the series), as received.
    series_id : str
        The series requested; names the CSV value column and fills ``series_id``.

    Returns
    -------
    pd.DataFrame
        Columns and dtypes of ``OBSERVATION_COLUMNS``, sorted by date. FRED's markers
        for a missing value (``"."`` or empty) become NaN.

    Raises
    ------
    FredParseError
        If the payload is neither format, or lacks the series or a date or value.
    """
    text = content.decode("utf-8").lstrip()
    if text.startswith("{"):
        dates, values = _from_json(text, series_id)
    else:
        dates, values = _from_csv(text, series_id)
    frame = pd.DataFrame(
        {
            "series_id": series_id,
            "date": pd.to_datetime(pd.Series(dates, dtype="string"), format="%Y-%m-%d"),
            "value": [
                float("nan") if v.strip() in MISSING else float(v) for v in values
            ],
        }
    )
    frame = frame[list(OBSERVATION_COLUMNS)].astype(OBSERVATION_COLUMNS)
    return frame.sort_values(["date"], kind="stable").reset_index(drop=True)


def load_fred(
    series_ids: Sequence[str],
    *,
    provider: DataProvider,
    store: SnapshotStore,
    as_of: date,
) -> pd.DataFrame:
    """Snapshot (if not stored yet) and parse each series; one table, in the order given."""
    frames = [
        parse_fred(fetch_snapshot(provider, series_id, as_of, store), series_id)
        for series_id in series_ids
    ]
    if not frames:
        return parse_fred(b'{"observations": []}', "")
    return pd.concat(frames, ignore_index=True)


def _from_json(text: str, series_id: str) -> tuple[list[str], list[str]]:
    """Return dates and raw values from an API JSON payload."""
    try:
        observations = cast(list[dict[str, Any]], json.loads(text)["observations"])
        return [str(o["date"]) for o in observations], [
            str(o["value"]) for o in observations
        ]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise FredParseError(
            f"{series_id}: not a FRED observations payload ({error})"
        ) from error


def _from_csv(text: str, series_id: str) -> tuple[list[str], list[str]]:
    """Return dates and raw values from a chart CSV (first column the date)."""
    table = pd.read_csv(io.StringIO(text), dtype="string", keep_default_na=False)
    if series_id not in table.columns or table.columns[0] == series_id:
        raise FredParseError(f"{series_id}: CSV has columns {list(table.columns)}")
    dates = table[table.columns[0]].tolist()
    values = table[series_id].tolist()
    return [str(d) for d in dates], [str(v) for v in values]
