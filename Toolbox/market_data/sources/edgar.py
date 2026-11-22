"""
market_data/sources/edgar.py
----------------------------
SEC EDGAR XBRL ``companyfacts``: every value a company has reported, with its filing.

The provider fetches one company's ``companyfacts`` JSON per CIK through the central
``ApiClient``; snapshots store it as received. The parser maps the tags in ``TAG_MAP``
to canonical fields and returns one row per reported value, keeping the filing date,
form, fiscal period and accession number so the point-in-time stage can pick the
values first reported before each rebalance date (spec §3.3, §3.5). SEC requires a
declared User-Agent (a name and an e-mail address) and at most 10 requests per second.

Owns
----
The EDGAR endpoint and headers, the ``companyfacts`` source model and its columns.

Must not
--------
Choose between tags, periods or restatements (point-in-time stage); compute ratios
(metrics layers); read the User-Agent from the environment (the command-line boundary).

Public API
----------
edgar_client(user_agent, *, max_requests_per_second, ...)
    An ``ApiClient`` with the headers SEC requires.
EdgarCompanyFacts(client)
    The ``DataProvider`` for ``companyfacts``; the query is a CIK.
EdgarSubmissions(client)
    The ``DataProvider`` for ``submissions``, a company's filing index.
latest_periodic_filing(content)
    The date of the latest 10-K or 10-Q in a ``submissions`` payload.
parse_tickers(content)
    The company's current ticker symbols from a ``submissions`` payload.
EdgarTickers(client)
    The ``DataProvider`` for SEC's list of current tickers and their CIKs.
parse_ticker_ciks(content)
    That list as a table: ``symbol``, ``cik``.
parse_companyfacts(content, tag_map)
    Raw JSON to one row per reported value of a mapped tag.
load_companyfacts(ciks, *, provider, store, as_of, tag_map)
    Snapshot and parse several companies into one table.
format_cik(cik)
    A CIK as the 10-digit, zero-padded string EDGAR uses.
COMPANYFACTS_COLUMNS, COMPANYFACTS_SCHEMA
    The columns and dtypes of the parsed facts, and their schema.
FACTS_TABLE_SCHEMA
    The schema of the stored facts table (the parsed facts plus ``snapshot_as_of``).

Dependency rule
---------------
pandas, the standard library, ``skatkis.io``, ``skatkis.pipelines`` and
``market_data.sources.tag_map``.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, cast

import pandas as pd

from Toolbox.market_data.sources.tag_map import TAG_MAP, FieldMap
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
    type_date,
    unique_key,
)

COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
PERIODIC_FORMS = frozenset({"10-K", "10-Q", "10-K/A", "10-Q/A"})
SEC_MAX_REQUESTS_PER_SECOND = 10.0
CIK_DIGITS = 10

COMPANYFACTS_COLUMNS: dict[str, str] = {
    "cik": "int64",
    "entity_name": "string",
    "field": "string",
    "taxonomy": "string",
    "tag": "string",
    "tag_priority": "int64",
    "unit": "string",
    "value": "float64",
    "period_start": "datetime64[ns]",
    "period_end": "datetime64[ns]",
    "fiscal_year": "Int64",
    "fiscal_period": "string",
    "form": "string",
    "filed": "datetime64[ns]",
    "accession": "string",
    "frame": "string",
}
"""Columns of the parsed table and their dtypes.

``tag_priority`` is the tag's position in its field's ``FieldMap.tags`` (0 = preferred).
``period_start`` is missing for balance-sheet values (instants). ``filed`` is the date
the filing was accepted by SEC. ``frame`` is SEC's calendar frame (e.g. ``CY2023Q4I``),
present only on the value SEC deems current for that period.
"""

COMPANYFACTS_SCHEMA: Schema = from_dtypes(
    COMPANYFACTS_COLUMNS,
    {
        "cik": required | unique_key | positive,
        "entity_name": required,
        "field": identifier
        | required
        | unique_key
        | allowed_values({f.field for f in TAG_MAP}),
        "taxonomy": identifier
        | required
        | allowed_values({taxonomy for f in TAG_MAP for taxonomy, _ in f.tags}),
        "tag": identifier
        | required
        | unique_key
        | allowed_values({tag for f in TAG_MAP for _, tag in f.tags}),
        "tag_priority": required | non_negative,
        "unit": identifier
        | required
        | unique_key
        | allowed_values({f.unit for f in TAG_MAP}),
        "value": required,
        "period_start": unique_key,
        "period_end": required | unique_key,
        "form": identifier | required,
        "filed": required,
        "accession": identifier | required | unique_key,
    },
)
"""The parsed facts: one row per reported value, keyed on the company, the filing, the
field and tag, the unit and the period (``period_start`` missing for an instant). Only
the fields, taxonomies, tags and units of ``TAG_MAP`` are allowed: the stored table is
parsed with the default map, which reads only those. The read gate checks them too, so a
table parsed under an earlier ``TAG_MAP`` is refused until it is parsed again;
``update_edgar`` parses each company's latest snapshot again on every run, a reused one
included. ``filed`` may
precede ``period_end`` (a dividend declared ahead, a share count on a cover page); the
value was public on ``filed``."""

FACTS_TABLE_SCHEMA: Schema = COMPANYFACTS_SCHEMA | {
    "snapshot_as_of": type_date | required
}
"""The stored facts table: the parsed facts plus ``snapshot_as_of``, the date of the
snapshot each row came from, which the update adds."""

_SORT_ORDER = ["field", "tag_priority", "period_end", "filed", "accession"]


class EdgarParseError(ValueError):
    """A ``companyfacts`` payload is malformed or reports a field in the wrong unit."""


def format_cik(cik: int | str) -> str:
    """Return ``cik`` as the 10-digit, zero-padded string EDGAR uses.

    Raises
    ------
    ValueError
        If ``cik`` is not a positive integer of at most 10 digits.
    """
    text = str(cik).strip()
    if not text.isdigit() or len(text) > CIK_DIGITS or int(text) == 0:
        raise ValueError(f"not a CIK: {cik!r}")
    return text.zfill(CIK_DIGITS)


def edgar_client(
    user_agent: str,
    *,
    max_requests_per_second: float,
    timeout_seconds: float,
    max_retries: int,
    backoff_seconds: float,
) -> ApiClient:
    """Return an ``ApiClient`` that sends the User-Agent SEC requires.

    Parameters
    ----------
    user_agent : str
        A name and contact e-mail address, e.g. ``"Jane Doe jane@example.com"``; read
        from the environment by the caller.
    max_requests_per_second : float
        At most 10 (SEC's limit).
    timeout_seconds, max_retries, backoff_seconds
        Passed to ``ApiClient``; values come from ``config/market_data.toml``.

    Raises
    ------
    ValueError
        If the User-Agent has no e-mail address or the rate exceeds SEC's limit.
    """
    if "@" not in user_agent:
        raise ValueError("the SEC User-Agent must contain a contact e-mail address")
    if max_requests_per_second > SEC_MAX_REQUESTS_PER_SECOND:
        raise ValueError(
            f"SEC allows at most {SEC_MAX_REQUESTS_PER_SECOND:g} requests per second"
        )
    return ApiClient(
        headers={"User-Agent": user_agent},
        max_requests_per_second=max_requests_per_second,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        backoff_seconds=backoff_seconds,
    )


@dataclass(frozen=True)
class EdgarCompanyFacts(DataProvider):
    """``DataProvider`` for EDGAR ``companyfacts``; the query is a CIK."""

    client: ApiClient
    url_template: str = COMPANYFACTS_URL

    @property
    def name(self) -> str:
        """Snapshot folder name: ``edgar_companyfacts``."""
        return "edgar_companyfacts"

    def fetch(self, query: str, as_of: date) -> RawPayload:
        """Return the ``companyfacts`` JSON for CIK ``query``.

        EDGAR serves only the current version, so ``as_of`` labels the snapshot; the
        filing date of each value is what makes the data point-in-time.
        """
        url = self.url_template.format(cik=format_cik(query))
        return RawPayload(content=self.client.get(url), extension="json")


@dataclass(frozen=True)
class EdgarSubmissions(DataProvider):
    """``DataProvider`` for EDGAR ``submissions``, a company's filing index; the query is a CIK."""

    client: ApiClient
    url_template: str = SUBMISSIONS_URL

    @property
    def name(self) -> str:
        """Snapshot folder name: ``edgar_submissions``."""
        return "edgar_submissions"

    def fetch(self, query: str, as_of: date) -> RawPayload:
        """Return the ``submissions`` JSON for CIK ``query``."""
        url = self.url_template.format(cik=format_cik(query))
        return RawPayload(content=self.client.get(url), extension="json")


def latest_periodic_filing(content: bytes) -> date | None:
    """Return the latest filing date of a 10-K or 10-Q (or amendment) in ``submissions``.

    Reads the ``filings.recent`` index, which holds a company's latest filings (at least
    a year, and up to 1,000). Returns ``None`` if it lists no periodic filing.

    Raises
    ------
    EdgarParseError
        If the payload is not ``submissions`` JSON.
    """
    try:
        recent = cast(dict[str, list[str]], json.loads(content)["filings"]["recent"])
        forms, dates = recent["form"], recent["filingDate"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise EdgarParseError(
            f"submissions payload lacks filings.recent ({error})"
        ) from error
    periodic = [
        date.fromisoformat(d)
        for f, d in zip(forms, dates, strict=True)
        if f in PERIODIC_FORMS
    ]
    return max(periodic, default=None)


def parse_tickers(content: bytes) -> list[str]:
    """Return the ticker symbols listed in a ``submissions`` payload (current, not historical).

    Raises
    ------
    EdgarParseError
        If the payload is not ``submissions`` JSON.
    """
    try:
        return [str(t) for t in cast(list[object], json.loads(content)["tickers"])]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise EdgarParseError(f"submissions payload lacks tickers ({error})") from error


@dataclass(frozen=True)
class EdgarTickers(DataProvider):
    """``DataProvider`` for SEC's list of current tickers; the query names the snapshot."""

    client: ApiClient
    url: str = TICKERS_URL

    @property
    def name(self) -> str:
        """Snapshot folder name: ``edgar_tickers``."""
        return "edgar_tickers"

    def fetch(self, query: str, as_of: date) -> RawPayload:
        """Return ``company_tickers.json``; SEC serves only today's list."""
        return RawPayload(content=self.client.get(self.url), extension="json")


def parse_ticker_ciks(content: bytes) -> pd.DataFrame:
    """Return SEC's current tickers with their CIKs.

    Returns
    -------
    pd.DataFrame
        Columns ``symbol`` (string, as SEC lists it: ``BRK-B``) and ``cik`` (Int64);
        a ticker listed twice keeps its first CIK.

    Raises
    ------
    EdgarParseError
        If the payload is not the ticker list.
    """
    try:
        entries = cast(dict[str, dict[str, Any]], json.loads(content)).values()
        rows = [(str(e["ticker"]), int(e["cik_str"])) for e in entries]
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as error:
        raise EdgarParseError(f"not SEC's ticker list ({error})") from error
    frame = pd.DataFrame(rows, columns=["symbol", "cik"]).drop_duplicates("symbol")
    return frame.astype({"symbol": "string", "cik": "Int64"}).reset_index(drop=True)


def parse_companyfacts(
    content: bytes, tag_map: Sequence[FieldMap] = TAG_MAP
) -> pd.DataFrame:
    """Return one row per reported value of every mapped tag in a ``companyfacts`` payload.

    Parameters
    ----------
    content : bytes
        The ``companyfacts`` JSON as received.
    tag_map : Sequence[FieldMap]
        Fields and tags to keep; unmapped tags are dropped.

    Returns
    -------
    pd.DataFrame
        Columns and dtypes of ``COMPANYFACTS_COLUMNS``, sorted by field, tag priority,
        period end, filing date and accession. Values are as filed: amendments and
        restatements appear as further rows, none is removed.

    Raises
    ------
    EdgarParseError
        If the payload is not ``companyfacts`` JSON, a fact lacks a required key
        (``end``, ``val``, ``accn``, ``form``, ``filed``), or a mapped tag is reported
        only in units other than its field's unit. The message names the CIK, tag and
        period.
    """
    try:
        document = json.loads(content)
    except json.JSONDecodeError as error:
        raise EdgarParseError(
            f"companyfacts payload is not valid JSON: {error}"
        ) from error
    if (
        not isinstance(document, dict)
        or "cik" not in document
        or "facts" not in document
    ):
        raise EdgarParseError("companyfacts payload lacks 'cik' or 'facts'")
    doc = cast(dict[str, Any], document)
    cik = int(doc["cik"])
    entity_name = str(doc.get("entityName", ""))
    facts = cast(dict[str, dict[str, Any]], doc["facts"])

    rows: list[dict[str, object]] = []
    for mapping in tag_map:
        for priority, (taxonomy, tag) in enumerate(mapping.tags):
            concept = facts.get(taxonomy, {}).get(tag)
            if concept is None:
                continue
            units = cast(
                dict[str, list[dict[str, Any]]], cast(dict[str, Any], concept)["units"]
            )
            if mapping.unit not in units:
                raise EdgarParseError(
                    f"CIK {cik:010d}: {taxonomy}:{tag} (field {mapping.field!r}) is reported "
                    f"in {sorted(units)}, expected {mapping.unit!r}"
                )
            for fact in units[mapping.unit]:
                try:
                    rows.append(
                        {
                            "cik": cik,
                            "entity_name": entity_name,
                            "field": mapping.field,
                            "taxonomy": taxonomy,
                            "tag": tag,
                            "tag_priority": priority,
                            "unit": mapping.unit,
                            "value": float(fact["val"]),
                            "period_start": fact.get("start"),
                            "period_end": fact["end"],
                            "fiscal_year": fact.get("fy"),
                            "fiscal_period": fact.get("fp"),
                            "form": fact["form"],
                            "filed": fact["filed"],
                            "accession": fact["accn"],
                            "frame": fact.get("frame"),
                        }
                    )
                except KeyError as error:
                    raise EdgarParseError(
                        f"CIK {cik:010d}: {taxonomy}:{tag} value for period ending "
                        f"{fact.get('end')} lacks {error}"
                    ) from error
    return _to_frame(rows)


def load_companyfacts(
    ciks: Sequence[int | str],
    *,
    provider: DataProvider,
    store: SnapshotStore,
    as_of: date,
    tag_map: Sequence[FieldMap] = TAG_MAP,
) -> pd.DataFrame:
    """Snapshot (if not stored yet) and parse ``companyfacts`` for each CIK.

    Parameters
    ----------
    ciks : Sequence[int | str]
        Companies to load.
    provider : DataProvider
        Normally ``EdgarCompanyFacts``.
    store : SnapshotStore
        Raw snapshot root (``data/raw``).
    as_of : date
        Snapshot date.
    tag_map : Sequence[FieldMap]
        Fields and tags to keep.

    Returns
    -------
    pd.DataFrame
        The rows of ``parse_companyfacts`` for every CIK, in the order given.
    """
    frames = [
        parse_companyfacts(
            fetch_snapshot(provider, format_cik(cik), as_of, store), tag_map
        )
        for cik in ciks
    ]
    if not frames:
        return _to_frame([])
    return pd.concat(frames, ignore_index=True)


def _to_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    """Build the parsed table with ``COMPANYFACTS_COLUMNS`` dtypes and sort order."""
    frame = pd.DataFrame(rows, columns=list(COMPANYFACTS_COLUMNS))
    for column in ("period_start", "period_end", "filed"):
        frame[column] = pd.to_datetime(frame[column], format="%Y-%m-%d")
    frame = frame.astype(COMPANYFACTS_COLUMNS)
    return frame.sort_values(_SORT_ORDER, kind="stable").reset_index(drop=True)
