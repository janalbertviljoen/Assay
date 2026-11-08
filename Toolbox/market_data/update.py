"""
market_data/update.py
---------------------
The update pipeline: brings the stored data up to an as-of date, one source at a time.

Each ``update_*`` function fetches what is missing through the sources, stores the raw
snapshots, and writes the parsed tables as Parquet under
``<interim>/<source>/<as_of>/``. EDGAR is updated incrementally: a company's filing
index is checked first, and its ``companyfacts`` are fetched again only if it has filed
a 10-K or 10-Q since its latest stored snapshot; otherwise that snapshot is reused.
Prices and the exchange rate are small and fetched in full for each as-of date. The
terminal command (``python -m Toolbox.market_data update``) calls these functions.

Every table passes the stored-table gate (``market_data.validation.check_table``)
against its schema in ``TABLE_SCHEMAS`` before it is written, so a malformed table never
reaches ``data/interim``. A company's facts and a symbol's prices, dividends and splits
are checked first on their own: one that breaks a constraint, or has a column too many
or too few, is left out and reported in ``UpdateResult.failed`` with the reason, like a
fetch or parse failure, and the rest of the update goes on. The combined tables are
checked again (a key repeated across companies or symbols), all of them before any is
written, so a failure there leaves the folder as it was.

Owns
----
Which sources are updated, the incremental EDGAR rule, the layout of the parsed tables
per as-of date, and the list of the stored tables with their schemas
(``TABLE_SCHEMAS``; each schema is owned by its source module).

Must not
--------
Parse vendor payloads (``market_data.sources``); clean or trim tables (cleaning stage);
read the environment or the clock (the command line passes keys and the as-of date).

Public API
----------
Storage(snapshots, interim)
    Where raw snapshots and parsed tables live.
update_edgar(ciks, *, as_of, storage, client)
    Fundamentals: incremental ``companyfacts`` per company; table ``facts``.
update_prices(tickers, *, as_of, storage, daily, monthly)
    Daily prices, and dividends and splits from monthly bars; tables ``prices``,
    ``dividends``, ``splits``.
update_fx(series_ids, *, as_of, storage, provider)
    FRED series; table ``observations``.
ticker_ciks(as_of, *, storage, client)
    SEC's current tickers and their CIKs, from a snapshot of the day.
update_constituents(as_of, *, storage, provider, index, pages, ticker_ciks)
    One index's members and changes; tables ``constituents`` and ``changes``.
UpdateResult
    What one update fetched, reused and wrote.
TABLE_SCHEMAS
    The schema of every stored table the update writes, by table name.

Dependency rule
---------------
pandas, the standard library, ``skatkis.io``, ``skatkis.pipelines``,
``market_data.sources`` and ``market_data.validation``.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from Toolbox.market_data.sources.constituents import (
    CHANGE_SCHEMA,
    CONSTITUENT_SCHEMA,
    WikipediaPage,
    parse_changes,
    parse_constituents,
)
from Toolbox.market_data.sources.edgar import (
    FACTS_TABLE_SCHEMA,
    EdgarCompanyFacts,
    EdgarSubmissions,
    EdgarTickers,
    format_cik,
    latest_periodic_filing,
    parse_companyfacts,
    parse_ticker_ciks,
)
from Toolbox.market_data.sources.fred import OBSERVATION_SCHEMA, FredSeries, load_fred
from Toolbox.market_data.sources.prices import (
    DIVIDEND_SCHEMA,
    LISTING_COLUMNS,
    LISTING_SCHEMA,
    PRICE_SCHEMA,
    SPLIT_SCHEMA,
    ChartTables,
    YahooChart,
    load_chart,
    yahoo_symbol,
)
from Toolbox.market_data.validation import check_table
from Toolbox.skatkis.io.api import ApiClient, ApiError
from Toolbox.skatkis.io.snapshots import SnapshotStore, fetch_snapshot, read_snapshot
from Toolbox.skatkis.io.tables import write_table
from Toolbox.skatkis.pipelines.contracts import Schema

TABLE_SCHEMAS: dict[str, Schema] = {
    "facts": FACTS_TABLE_SCHEMA,
    "prices": PRICE_SCHEMA,
    "dividends": DIVIDEND_SCHEMA,
    "splits": SPLIT_SCHEMA,
    "listings": LISTING_SCHEMA,
    "constituents": CONSTITUENT_SCHEMA,
    "changes": CHANGE_SCHEMA,
    "observations": OBSERVATION_SCHEMA,
}
"""The schema of every stored table the update writes, by its file name under
``<interim>/<source>/<as_of>/``; each is owned by its source module."""


@dataclass(frozen=True)
class Storage:
    """Where an update reads and writes.

    Parameters
    ----------
    snapshots : SnapshotStore
        Raw snapshots (``data/raw``).
    interim : Path
        Parsed tables (``data/interim``).
    """

    snapshots: SnapshotStore
    interim: Path

    def folder(self, source: str, as_of: date) -> Path:
        """Return the table folder ``<interim>/<source>/<as_of>``."""
        return self.interim / source / as_of.isoformat()


@dataclass(frozen=True)
class UpdateResult:
    """What one source's update did.

    Parameters
    ----------
    source : str
        Source name, also the folder of its tables under ``interim``.
    fetched : tuple[str, ...]
        Queries fetched from the API in this run.
    reused : tuple[str, ...]
        Queries served from an earlier snapshot that is still current.
    tables : dict[str, int]
        Row count of each table written.
    folder : Path
        Where the tables were written.
    failed : dict[str, str]
        Queries that could not be fetched or parsed, or whose table failed its schema,
        with the reason; the rest of the update goes on without them.
    """

    source: str
    fetched: tuple[str, ...]
    reused: tuple[str, ...]
    tables: dict[str, int]
    folder: Path
    failed: dict[str, str] = field(default_factory=dict[str, str])


def update_edgar(
    ciks: Sequence[int | str], *, as_of: date, storage: Storage, client: ApiClient
) -> UpdateResult:
    """Bring EDGAR fundamentals up to ``as_of`` and write the ``facts`` table.

    Parameters
    ----------
    ciks : Sequence[int | str]
        Companies to update.
    as_of : date
        The update date.
    storage : Storage
        Snapshot and table roots.
    client : ApiClient
        From ``edgar_client``, with the SEC User-Agent.

    Returns
    -------
    UpdateResult
        Companies fetched and reused; the ``facts`` table at
        ``<interim>/edgar_companyfacts/<as_of>/facts.parquet``.

    Notes
    -----
    A company's ``companyfacts`` are fetched again when it has no stored snapshot, or
    when its latest 10-K or 10-Q was filed on or after the date of its latest snapshot
    (a filing on the snapshot day itself may be newer than the snapshot). The table has
    the columns of ``COMPANYFACTS_COLUMNS`` plus ``snapshot_as_of``, the date of the
    snapshot each row came from.
    """
    store = storage.snapshots
    facts_provider = EdgarCompanyFacts(client)
    submissions_provider = EdgarSubmissions(client)
    fetched: list[str] = []
    reused: list[str] = []
    frames: list[pd.DataFrame] = []
    failed: dict[str, str] = {}
    for cik in ciks:
        query = format_cik(cik)
        try:
            previous = store.latest_as_of(
                facts_provider.name, query, on_or_before=as_of
            )
            latest_filing = latest_periodic_filing(
                fetch_snapshot(submissions_provider, query, as_of, store)
            )
            if previous is not None and (
                latest_filing is None or latest_filing < previous
            ):
                content = read_snapshot(store, facts_provider.name, query, previous)
                snapshot_as_of, done = previous, reused
            else:
                content = fetch_snapshot(facts_provider, query, as_of, store)
                snapshot_as_of, done = as_of, fetched
            frame = parse_companyfacts(content)
            frame["snapshot_as_of"] = pd.Timestamp(snapshot_as_of)
            # Per company, so one bad filing loses that company, not the update.
            check_table(frame, TABLE_SCHEMAS["facts"], f"facts of CIK {query}")
        # ValueError covers parse errors, schema breaches and a column mismatch.
        except (ApiError, ValueError) as error:
            failed[query] = str(error)
            continue
        done.append(query)
        frames.append(frame)
    facts = pd.concat(frames, ignore_index=True) if frames else _empty_facts()
    folder = storage.folder(facts_provider.name, as_of)
    _write_all({"facts": facts}, folder)
    return UpdateResult(
        source=facts_provider.name,
        fetched=tuple(fetched),
        reused=tuple(reused),
        tables={"facts": len(facts)},
        folder=folder,
        failed=failed,
    )


def update_prices(
    tickers: Sequence[str],
    *,
    as_of: date,
    storage: Storage,
    daily: YahooChart,
    monthly: YahooChart,
) -> UpdateResult:
    """Fetch prices, dividends and splits up to ``as_of`` and write their tables.

    Parameters
    ----------
    tickers : Sequence[str]
        Symbols, including any benchmark such as ``^SP500TR``.
    as_of : date
        The update date.
    storage : Storage
        Snapshot and table roots.
    daily : YahooChart
        Daily bars from the start of the analysis period; gives the prices.
    monthly : YahooChart
        Monthly bars over a longer period; gives the dividends, the splits and the date
        each symbol's history starts.

    Returns
    -------
    UpdateResult
        Tables ``prices``, ``dividends``, ``splits`` and ``listings`` (``symbol``,
        ``first_date``: the first monthly bar, no earlier than the monthly provider's
        start) at ``<interim>/yahoo/<as_of>/``.
    """
    store = storage.snapshots
    stored = [
        t
        for t in tickers
        if store.latest_as_of(daily.name, yahoo_symbol(t), as_of) == as_of
    ]
    parsed: list[tuple[ChartTables, ChartTables]] = []
    failed: dict[str, str] = {}
    for ticker in tickers:
        try:
            bars = load_chart([ticker], provider=daily, store=store, as_of=as_of)
            months = load_chart([ticker], provider=monthly, store=store, as_of=as_of)
            # Per symbol, so one bad bar loses that symbol, not the update.
            for name, table in (
                ("prices", bars.prices),
                ("dividends", months.dividends),
                ("splits", months.splits),
            ):
                check_table(table, TABLE_SCHEMAS[name], f"{name} of {ticker}")
            parsed.append((bars, months))
        # ValueError covers parse errors, schema breaches and a column mismatch.
        except (ApiError, ValueError) as error:
            failed[ticker] = str(error)
    empty = load_chart([], provider=daily, store=store, as_of=as_of)
    folder = storage.folder("yahoo", as_of)
    tables = {
        "prices": _concat([d.prices for d, _ in parsed], empty.prices),
        "dividends": _concat([m.dividends for _, m in parsed], empty.dividends),
        "splits": _concat([m.splits for _, m in parsed], empty.splits),
        "listings": _listings([m.prices for _, m in parsed]),
    }
    _write_all(tables, folder)
    return UpdateResult(
        source="yahoo",
        fetched=tuple(t for t in tickers if t not in stored and t not in failed),
        reused=tuple(t for t in stored if t not in failed),
        tables={name: len(table) for name, table in tables.items()},
        folder=folder,
        failed=failed,
    )


def _listings(monthly: Sequence[pd.DataFrame]) -> pd.DataFrame:
    """Return each symbol's first monthly bar: columns ``symbol``, ``first_date``."""
    frames = [m[["symbol", "date"]] for m in monthly if not m.empty]
    if not frames:
        return pd.DataFrame(columns=list(LISTING_COLUMNS)).astype(LISTING_COLUMNS)
    first: pd.Series = pd.concat(frames).groupby("symbol")["date"].min()
    return pd.DataFrame(
        {
            "symbol": pd.Series(first.index.astype(str), dtype="string"),
            "first_date": first.to_numpy(),
        }
    )


def ticker_ciks(as_of: date, *, storage: Storage, client: ApiClient) -> pd.DataFrame:
    """Return SEC's current tickers and CIKs (``parse_ticker_ciks``), snapshotted on ``as_of``."""
    content = fetch_snapshot(
        EdgarTickers(client), "company_tickers", as_of, storage.snapshots
    )
    return parse_ticker_ciks(content)


def update_constituents(  # noqa: PLR0913  one keyword per input of the update
    as_of: date,
    *,
    storage: Storage,
    provider: WikipediaPage,
    index: str,
    pages: tuple[str, str],
    ticker_ciks: pd.DataFrame | None = None,
) -> UpdateResult:
    """Fetch one index's members and changes and write their tables.

    Parameters
    ----------
    as_of : date
        The update date.
    storage : Storage
        Snapshot and table roots.
    provider : WikipediaPage
        The Wikipedia provider.
    index : str
        The index key (``sp500``), the folder of its tables.
    pages : tuple[str, str]
        The page titles of the members and of the changes (may be the same page).
    ticker_ciks : pd.DataFrame, optional
        ``parse_ticker_ciks`` output; fills the CIK of members whose page gives none,
        matched on the symbol in SEC's form (``BRK.B`` as ``BRK-B``).

    Returns
    -------
    UpdateResult
        Tables ``constituents`` and ``changes`` at
        ``<interim>/constituents/<as_of>/<index>/``.
    """
    store = storage.snapshots
    stored = [p for p in pages if store.latest_as_of(provider.name, p, as_of) == as_of]
    members_page, changes_page = pages
    constituents = parse_constituents(
        fetch_snapshot(provider, members_page, as_of, store)
    )
    if ticker_ciks is not None:
        known = ticker_ciks.set_index("symbol")["cik"]
        sec = constituents["symbol"].str.replace(".", "-", regex=False)
        constituents["cik"] = constituents["cik"].fillna(
            pd.Series(known.reindex(sec).to_numpy(), index=constituents.index)
        )
    changes = parse_changes(fetch_snapshot(provider, changes_page, as_of, store))
    folder = storage.folder("constituents", as_of) / index
    _write_all({"constituents": constituents, "changes": changes}, folder)
    return UpdateResult(
        source="constituents",
        fetched=tuple(p for p in dict.fromkeys(pages) if p not in stored),
        reused=tuple(dict.fromkeys(stored)),
        tables={"constituents": len(constituents), "changes": len(changes)},
        folder=folder,
    )


def update_fx(
    series_ids: Sequence[str], *, as_of: date, storage: Storage, provider: FredSeries
) -> UpdateResult:
    """Fetch FRED series up to ``as_of`` and write the ``observations`` table.

    Returns
    -------
    UpdateResult
        Table ``observations`` at ``<interim>/fred/<as_of>/observations.parquet``.
    """
    stored = [
        s
        for s in series_ids
        if storage.snapshots.latest_as_of(provider.name, s, as_of) == as_of
    ]
    observations = load_fred(
        series_ids, provider=provider, store=storage.snapshots, as_of=as_of
    )
    folder = storage.folder(provider.name, as_of)
    _write_all({"observations": observations}, folder)
    return UpdateResult(
        source=provider.name,
        fetched=tuple(s for s in series_ids if s not in stored),
        reused=tuple(stored),
        tables={"observations": len(observations)},
        folder=folder,
    )


def _write_all(tables: Mapping[str, pd.DataFrame], folder: Path) -> None:
    """Check every table against its schema in ``TABLE_SCHEMAS``, then write them all.

    All are checked before any is written, so a failing table leaves the folder as it
    was rather than half updated.
    """
    for name, table in tables.items():
        check_table(table, TABLE_SCHEMAS[name], f"{folder}/{name}")
    for name, table in tables.items():
        write_table(table, folder / f"{name}.parquet")


def _concat(frames: list[pd.DataFrame], empty: pd.DataFrame) -> pd.DataFrame:
    """Concatenate ``frames``, or return ``empty`` when there are none."""
    return pd.concat(frames, ignore_index=True) if frames else empty


def _empty_facts() -> pd.DataFrame:
    """Return an empty ``facts`` table with its columns and dtypes."""
    frame = parse_companyfacts(b'{"cik": 0, "facts": {}}')
    frame["snapshot_as_of"] = pd.Series(dtype="datetime64[ns]")
    return frame
