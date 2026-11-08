"""
market_data/sources/constituents.py
-----------------------------------
Index membership from Wikipedia: the current members with their GICS classification,
and the history of additions and removals.

The provider fetches a page's wikitext through the MediaWiki API with the central
``ApiClient``; snapshots store the JSON as received. Per index (``config/indices.toml``)
two tables are read: the members (``id="constituents"``: symbol, security, GICS sector
and sub-industry, and where the page has them the date added and the CIK) and the
changes (``id="changes"``: effective date, symbol added, symbol removed, reason), on
one page or two. Member columns are found by their header, since the pages differ (the
S&P 400 page has no CIK column, only an SEC link). The CIK links a member to its EDGAR
filings; the GICS sector is the grouping used for analysis.

Owns
----
The MediaWiki endpoint, the wikitext table parsing, and the constituents and changes
source models with their columns.

Must not
--------
Reconstruct the membership at a past date or exclude sectors (the universe stage);
fetch filings or prices (other sources).

Public API
----------
wikipedia_client(*, max_requests_per_second, ...)
    An ``ApiClient`` for the MediaWiki API.
WikipediaPage(client)
    The ``DataProvider`` for one page's wikitext; the query is the page title.
parse_constituents(content)
    The current members table, columns found by header.
parse_changes(content)
    The additions and removals table.
CONSTITUENT_SCHEMA, CHANGE_SCHEMA
    The schemas of the two tables.

Dependency rule
---------------
pandas, the standard library, ``skatkis.io`` and ``skatkis.pipelines``.
"""

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, cast

import pandas as pd

from Toolbox.skatkis.io.api import ApiClient
from Toolbox.skatkis.io.provider import DataProvider, RawPayload
from Toolbox.skatkis.pipelines.contracts import Schema
from Toolbox.skatkis.pipelines.schema import (
    from_dtypes,
    identifier,
    positive,
    required,
    unique_key,
)

API_URL = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "trading-bot/0.1 (personal research; index membership)"
CHANGE_CELLS = 6

CONSTITUENT_COLUMNS: dict[str, str] = {
    "symbol": "string",
    "security": "string",
    "gics_sector": "string",
    "gics_sub_industry": "string",
    "date_added": "datetime64[ns]",
    "cik": "Int64",
}
"""Current members: ``symbol`` as listed (``BRK.B``), GICS sector and sub-industry,
the date the company joined the index (missing where the page does not give it) and its
CIK (missing where the page gives none)."""

CHANGE_COLUMNS: dict[str, str] = {
    "date": "datetime64[ns]",
    "added_symbol": "string",
    "added_security": "string",
    "removed_symbol": "string",
    "removed_security": "string",
    "reason": "string",
}
"""Index changes on their effective date; an addition or a removal may be missing."""

CONSTITUENT_SCHEMA: Schema = from_dtypes(
    CONSTITUENT_COLUMNS,
    {
        "symbol": identifier | required | unique_key,
        "security": required,
        "gics_sector": identifier | required,
        "gics_sub_industry": identifier | required,
        "cik": positive,
    },
)
"""The members table: one row per listed symbol (two share classes of one company share
a CIK); ``date_added`` and ``cik`` may be missing, as the page gives them."""

CHANGE_SCHEMA: Schema = from_dtypes(CHANGE_COLUMNS, {"date": required})
"""The changes table: no key, since one date may carry several changes."""


class ConstituentsParseError(ValueError):
    """A wikitext payload lacks the expected table."""


def wikipedia_client(
    *,
    max_requests_per_second: float,
    timeout_seconds: float,
    max_retries: int,
    backoff_seconds: float,
) -> ApiClient:
    """Return an ``ApiClient`` with a descriptive User-Agent, as Wikimedia asks.

    Parameters come from ``config/market_data.toml`` (``[sources.wikipedia]``).
    """
    return ApiClient(
        headers={"User-Agent": USER_AGENT},
        max_requests_per_second=max_requests_per_second,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        backoff_seconds=backoff_seconds,
    )


@dataclass(frozen=True)
class WikipediaPage(DataProvider):
    """``DataProvider`` for a Wikipedia page's wikitext; the query is the page title."""

    client: ApiClient

    @property
    def name(self) -> str:
        """Snapshot folder name: ``wikipedia``."""
        return "wikipedia"

    def fetch(self, query: str, as_of: date) -> RawPayload:
        """Return the MediaWiki ``parse`` JSON with the page's current wikitext.

        Wikipedia serves the current revision, so ``as_of`` labels the snapshot.
        """
        params = {
            "action": "parse",
            "page": query,
            "prop": "wikitext",
            "format": "json",
            "formatversion": "2",
        }
        return RawPayload(content=self.client.get(API_URL, params), extension="json")


def parse_constituents(content: bytes) -> pd.DataFrame:
    """Return the current members from an index's member list payload.

    Returns
    -------
    pd.DataFrame
        Columns and dtypes of ``CONSTITUENT_COLUMNS``, sorted by ``symbol``.

    Raises
    ------
    ConstituentsParseError
        If the payload has no table with ``id="constituents"``, or the table lacks a
        symbol, security or GICS column.

    Notes
    -----
    ``date_added`` is missing when the page has no "Date added" column. The CIK comes
    from the "CIK" column, else from the ``CIK=`` number in the "SEC filings" link;
    a link that gives the ticker instead leaves it missing.
    """
    wikitext = _wikitext(content)
    header = _header(wikitext, "constituents")
    needed = ("symbol", "security", "gics sector", "gics sub-industry")
    missing = [name for name in needed if name not in header]
    if missing:
        raise ConstituentsParseError(f"members table lacks {', '.join(missing)}")
    rows = [
        cells
        for cells in _table_rows(wikitext, "constituents")
        if len(cells) >= len(header)
    ]

    def cell(cells: list[str], name: str) -> str:
        return cells[header[name]] if name in header else ""

    frame = pd.DataFrame(
        {
            "symbol": [_symbol(cell(c, "symbol")) for c in rows],
            "security": [_plain(cell(c, "security")) for c in rows],
            "gics_sector": [_plain(cell(c, "gics sector")) for c in rows],
            "gics_sub_industry": [_plain(cell(c, "gics sub-industry")) for c in rows],
            "date_added": [_date(cell(c, "date added")) for c in rows],
            "cik": [_cik(cell(c, "cik"), cell(c, "sec filings")) for c in rows],
        }
    )
    frame = frame.astype(CONSTITUENT_COLUMNS)
    return frame.sort_values("symbol", kind="stable").reset_index(drop=True)


def parse_changes(content: bytes) -> pd.DataFrame:
    """Return the index changes from the payload with the ``id="changes"`` table.

    Returns
    -------
    pd.DataFrame
        Columns and dtypes of ``CHANGE_COLUMNS``, newest first as on the page. A row
        whose first cell is not a date continues a date cell spanning several rows and
        takes the date of the row above.

    Raises
    ------
    ConstituentsParseError
        If the payload has no table with ``id="changes"``.
    """
    records: list[dict[str, object]] = []
    previous_date: pd.Timestamp | None = None
    for row in _table_rows(_wikitext(content), "changes"):
        cells = row
        if row and _date(row[0]) is None and previous_date is not None:
            cells = [previous_date.strftime("%B %d, %Y"), *row]
        if len(cells) < CHANGE_CELLS:
            continue
        day = _date(cells[0])
        if day is None:
            continue
        previous_date = day
        records.append(
            {
                "date": day,
                "added_symbol": _plain(cells[1]) or None,
                "added_security": _plain(cells[2]) or None,
                "removed_symbol": _plain(cells[3]) or None,
                "removed_security": _plain(cells[4]) or None,
                "reason": _plain(cells[5]) or None,
            }
        )
    frame = pd.DataFrame(records, columns=list(CHANGE_COLUMNS))
    return frame.astype(CHANGE_COLUMNS).reset_index(drop=True)


def _wikitext(content: bytes) -> str:
    """Return the wikitext from a MediaWiki ``parse`` payload."""
    try:
        return str(cast(dict[str, Any], json.loads(content))["parse"]["wikitext"])
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise ConstituentsParseError(
            f"not a MediaWiki parse payload ({error})"
        ) from error


def _table_rows(wikitext: str, table_id: str) -> list[list[str]]:
    """Return the data rows of the wikitext table with ``id=table_id`` as lists of cells."""
    start = wikitext.find(f'id="{table_id}"')
    if start < 0:
        raise ConstituentsParseError(f'no table with id="{table_id}"')
    end = wikitext.find("\n|}", start)
    rows: list[list[str]] = []
    for block in wikitext[start:end].split("\n|-")[1:]:
        lines = [line for line in block.split("\n") if line.startswith("|")]
        if not lines:
            continue
        cells: list[str] = []
        for line in lines:
            cells.extend(part for part in re.split(r"\|\|", line.lstrip("|")))
        rows.append([_drop_attributes(cell) for cell in cells])
    return rows


def _header(wikitext: str, table_id: str) -> dict[str, int]:
    """Return each header cell's lower-case text and its column position."""
    start = wikitext.find(f'id="{table_id}"')
    if start < 0:
        raise ConstituentsParseError(f'no table with id="{table_id}"')
    end = wikitext.find("\n|}", start)
    for block in wikitext[start:end].split("\n|-")[1:]:
        lines = [line for line in block.split("\n") if line.startswith("!")]
        if lines:
            cells = [
                part for line in lines for part in re.split(r"!!", line.lstrip("!"))
            ]
            return {_plain(_drop_attributes(c)).lower(): i for i, c in enumerate(cells)}
    return {}


def _cik(column: str, link: str) -> int | None:
    """Return the CIK from its own cell, else from the ``CIK=`` number of an SEC link."""
    if (digits := _plain(column)).isdigit():
        return int(digits)
    match = re.search(r"CIK=0*(\d+)\b", link)
    return int(match.group(1)) if match else None


def _drop_attributes(cell: str) -> str:
    """Remove a leading cell attribute such as ``rowspan="2" |``."""
    match = re.match(r'^\s*[a-z-]+="[^"]*"\s*\|(?!\|)(.*)$', cell, flags=re.S)
    return match.group(1) if match else cell


def _plain(cell: str) -> str:
    """Return a cell's text without references, links or templates."""
    text = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", cell, flags=re.S)
    text = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _symbol(cell: str) -> str:
    """Return the ticker from a cell such as ``{{NyseSymbol|MMM}}`` or ``{{BZX link|CBOE}}``."""
    match = re.search(r"\{\{\s*\w*(?:Symbol| link)\s*\|\s*([^}|]+)", cell)
    return (match.group(1) if match else _plain(cell)).strip()


def _date(cell: str) -> pd.Timestamp | None:
    """Return the date in a cell (ISO or "October 6, 2026"), or ``None``."""
    text = _plain(cell)
    for fmt in ("%Y-%m-%d", "%B %d, %Y"):
        try:
            return pd.Timestamp(pd.to_datetime(text, format=fmt))
        except ValueError:
            continue
    return None
