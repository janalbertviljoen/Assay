"""
value_investing/io.py
---------------------
Reads the stored tables an index's commands use, each through its schema gate, and
assembles what the short buy report shows.

The terminal commands (``value_investing.__main__``) and other tools that show the picks
(``financial_planning``) call these instead of reading files themselves; the results folder is the
caller's, never decided here.

Owns
----
The stored-table layout of an index (``StoredIndex``), the gated reads and the buy
report's inputs.

Must not
--------
Score, rank or hold (``value_investing.pipeline``, ``evaluation``, ``holding``); compute
the buy list (``value_investing.buying``, ``buy_list``); write anything but the buy
report's figures into the folder it is given.

Public API
----------
StoredIndex(key, label, benchmark, benchmark_name, membership, interim, tables, members, buy_list)
    An index of ``config/indices.toml`` and the folders of its stored tables.
stored_index(key, as_of_date, data_dir, indices)
    The ``StoredIndex`` of ``key`` for an as-of date.
read_input(folder, name)
    A stored table the pipeline reads, checked against ``INPUT_TABLES``.
read_report_table(folder, name)
    A stored table only the reports read, checked against ``REPORT_TABLES``.
company_names(path)
    Each company's full name by price symbol.
buy_report_inputs(*, as_of, rules, index, data_dir, indices, report_text, folder, amounts)
    The short buy report's inputs, its figures saved in ``folder``.
assemble_buy_list(prices, upcoming, end, settings, folder, rates)
    The buy list with each company's trend and the saved trend figure.

Dependency rule
---------------
pandas, ``skatkis.io``, ``market_data`` (validation, symbols) and ``value_investing``.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from Toolbox.market_data.sources.prices import yahoo_symbol
from Toolbox.market_data.validation import check_table
from Toolbox.skatkis.io.config import load_config
from Toolbox.skatkis.io.figures import save_figure
from Toolbox.skatkis.io.tables import read_table
from Toolbox.value_investing import buying, plots, report
from Toolbox.value_investing.schema import INPUT_TABLES, REPORT_TABLES


@dataclass(frozen=True)
class StoredIndex:
    """The index a command works on and where its stored tables live.

    ``buy_list`` says whether its reports show the personal buy list (``buy_list = true``
    in ``config/indices.toml``; off by default).
    """

    key: str
    label: str
    benchmark: str
    benchmark_name: str
    membership: str
    interim: Path
    tables: Path
    members: Path
    buy_list: bool = False


def stored_index(
    key: str, as_of_date: date, data_dir: Path, indices: Path
) -> StoredIndex:
    """Return the entry ``key`` of ``indices`` and its folders for ``as_of_date``.

    Parameters
    ----------
    key : str
        The index's table in ``indices``, e.g. ``sp500``.
    as_of_date : date
        The as-of date of the stored tables.
    data_dir : Path
        The data folder; the tables are under ``data_dir / "interim"``.
    indices : Path
        ``config/indices.toml``.

    Returns
    -------
    StoredIndex
        ``tables`` = ``interim/value_investing/<as_of>/<key>``, ``members`` =
        ``interim/constituents/<as_of>/<key>``; ``buy_list`` is False when the entry
        does not set it. The folders are not checked to exist.

    Raises
    ------
    KeyError
        When ``key`` or one of its ``label``, ``benchmark``, ``benchmark_name`` and
        ``membership`` is missing from ``indices``.
    """
    entry = load_config(indices)[key]
    as_of = as_of_date.isoformat()
    interim = data_dir / "interim"
    return StoredIndex(
        key=key,
        label=str(entry["label"]),
        benchmark=str(entry["benchmark"]),
        benchmark_name=str(entry["benchmark_name"]),
        membership=str(entry["membership"]),
        interim=interim,
        tables=interim / "value_investing" / as_of / key,
        members=interim / "constituents" / as_of / key,
        buy_list=bool(entry.get("buy_list", False)),
    )


def buy_report_inputs(  # noqa: PLR0913  one keyword per input the command reads
    *,
    as_of: date,
    rules: dict[str, Any],
    index: str,
    data_dir: Path,
    indices: Path,
    report_text: Path,
    folder: Path,
    amounts: Mapping[str, Any] | None = None,
) -> report.BuyReport:
    """Read the stored tables of ``as_of`` and return what the buy report shows.

    Used by the ``buy`` command and by ``financial_planning``'s personal report. Reads the first
    universe view's buyability table, the Yahoo prices, the FRED observations and the
    constituents of ``index``; the end date is the benchmark's last price date.

    Parameters
    ----------
    as_of : date
        The as-of date of the stored tables.
    rules : dict[str, Any]
        ``config/rules.toml`` (``[universe]``, ``[wallet]``, ``[ledger]``,
        ``[report]`` and ``[report.buy_list]``).
    index : str
        The index's key in ``indices``. Its ``buy_list`` flag is not read here: the
        buy report always shows the buy list.
    data_dir : Path
        The data folder (``data``).
    indices : Path
        ``config/indices.toml``.
    report_text : Path
        The report text (``config/report_value_investing.toml``); only its
        ``[sectors]`` are read here.
    folder : Path
        Where the figures are saved: ``next_prices.png`` and ``trends.png``.
    amounts : Mapping[str, Any] | None
        The investor's ``currency``, ``picks_amount`` and ``fixed``, replacing those
        of ``[report.buy_list]`` (``rules.toml`` holds a neutral default in USD with
        nothing fixed; ``financial_planning`` passes the private amounts). Any other key given
        replaces the setting of the same name too. ``None`` keeps ``rules``.

    Returns
    -------
    report.BuyReport
        The buy list with the trend states and figure, the next picks, the company
        names, the index label, the sector names and the price-history figure.

    Raises
    ------
    KeyError
        When ``index`` or a setting is missing.
    FileNotFoundError
        When a stored table is missing, including the FRED observations, which are
        read only when the buy list's currency is not USD.
    """
    entry = stored_index(index, as_of, data_dir, indices)
    settings = {**rules["report"]["buy_list"], **(amounts or {})}
    merged = {**rules, "report": {**rules["report"], "buy_list": settings}}
    return _buy_report_inputs(as_of.isoformat(), merged, entry, report_text, folder)


def _buy_report_inputs(
    as_of: str,
    rules: dict[str, Any],
    index: StoredIndex,
    report_text: Path,
    folder: Path,
) -> report.BuyReport:
    """Return the buy report's inputs for ``index`` (``buy_report_inputs``)."""
    view = str(rules["universe"]["views"][0])
    table = read_table(index.tables / f"buyability_{view}.parquet")
    prices = read_input(index.interim / "yahoo" / as_of, "prices")
    settings = rules["report"]
    rates = (
        read_report_table(index.interim / "fred" / as_of, "observations")
        if settings["buy_list"]["currency"] != "USD"
        else None
    )
    end = pd.Timestamp(prices[prices["symbol"] == index.benchmark]["date"].max())
    model = buying.report_wallet(rules)
    upcoming, _ = buying.next_picks(table, end, model, str(settings["share_column"]))
    buy = assemble_buy_list(prices, upcoming, end, settings["buy_list"], folder, rates)
    traded = buying.earlier_trades(
        table, prices, rules, model, end=end, benchmark=index.benchmark
    )
    years = int(settings["pick_years"])
    window = prices[
        prices["symbol"].isin(upcoming["symbol"])
        & (prices["date"] > end - pd.DateOffset(years=years))
        & (prices["date"] <= end)
    ]
    history = save_figure(
        plots.next_prices(window, traded, upcoming, years), folder / "next_prices.png"
    )
    return report.BuyReport(
        buy=buy,
        next_picks=upcoming,
        names=company_names(index.members / "constituents.parquet"),
        index_label=index.label,
        sectors=load_config(report_text)["sectors"],
        prices_figure=history,
        pick_years=years,
        pick_scenario=int(settings["pick_scenario"]),
    )


def assemble_buy_list(  # noqa: PLR0913, PLR0917  one argument per table the list reads
    prices: pd.DataFrame,
    upcoming: pd.DataFrame,
    end: pd.Timestamp,
    settings: dict[str, Any],
    folder: Path,
    rates: pd.DataFrame | None,
) -> report.BuyList:
    """Return the buy list with each company's trend state and the saved trend figure.

    Parameters
    ----------
    prices : pd.DataFrame
        Daily prices (``symbol``, ``date``, ``close``).
    upcoming : pd.DataFrame
        The next picks (``buying.next_picks``).
    end : pd.Timestamp
        The decision date; later prices and rates are not used.
    settings : dict[str, Any]
        ``[report.buy_list]`` with the investor's amounts (``buying.prepare_buy_list``)
        and the figure's ``years``, ``slope_years`` and ``slide``.
    folder : Path
        Where ``trends.png`` is saved.
    rates : pd.DataFrame or None
        FRED observations; needed, and used, only when the currency is not USD.

    Returns
    -------
    report.BuyList
        The orders, the trend states, ``settings`` with ``rate`` (units of the
        currency per USD, 1 for USD) and ``rate_date`` (the rate's date, ``end`` for
        USD), and the figure's path.

    Raises
    ------
    IndexError
        When ``settings["fx_series"]`` has no value on or before ``end``
        (``buying.latest_rate``), or a company has too short a history
        (``buying.prepare_buy_list``).
    """
    rate, rate_date = 1.0, end
    if settings["currency"] != "USD":
        if rates is None:
            raise ValueError(f"a {settings['currency']} buy list needs the FRED rates")
        rate, rate_date = buying.latest_rate(rates, str(settings["fx_series"]), end)
    orders, states, trends = buying.prepare_buy_list(
        prices, upcoming, end, settings, rate
    )
    symbols = [str(s) for s in orders["symbol"]]
    figure = save_figure(
        plots.price_trends(
            trends,
            symbols,
            years=int(settings["years"]),
            slope_years=int(settings["slope_years"]),
            slide=float(settings["slide"]),
        ),
        folder / "trends.png",
    )
    return report.BuyList(
        orders, states, {**settings, "rate": rate, "rate_date": rate_date}, figure
    )


def read_input(folder: Path, name: str) -> pd.DataFrame:
    """Read the stored table ``name`` from ``folder`` and check it against its schema.

    Parameters
    ----------
    folder : Path
        The folder holding ``<name>.parquet``.
    name : str
        A key of ``value_investing.schema.INPUT_TABLES`` (``prices``, ``facts``, ...).

    Returns
    -------
    pd.DataFrame
        The table as stored, unchanged by the check.

    Raises
    ------
    KeyError
        When ``name`` is not in ``INPUT_TABLES``.
    FileNotFoundError
        When the file is missing.
    ValueError
        When the table breaks its schema (``market_data.validation.check_table``: a
        missing or undeclared column, or a broken constraint).
    """
    table = read_table(folder / f"{name}.parquet")
    check_table(table, INPUT_TABLES[name], f"{folder}/{name}")
    return table


def read_report_table(folder: Path, name: str) -> pd.DataFrame:
    """Read a stored table only the reports read and check it against its schema.

    As ``read_input``, with ``name`` a key of ``value_investing.schema.REPORT_TABLES``
    (``observations``: the FRED exchange rates of the buy list). Kept apart so the
    pipeline's inputs stay exactly what it reads.
    """
    table = read_table(folder / f"{name}.parquet")
    check_table(table, REPORT_TABLES[name], f"{folder}/{name}")
    return table


def company_names(path: Path) -> dict[str, str]:
    """Return each company's full name by price symbol, from the constituents table.

    Parameters
    ----------
    path : Path
        The constituents table, ``<folder>/constituents.parquet``; read through
        ``read_input``, so it is checked against its schema.

    Returns
    -------
    dict[str, str]
        ``security`` by Yahoo symbol (``market_data.sources.prices.yahoo_symbol``,
        e.g. ``BRK.B`` becomes ``BRK-B``). Companies outside today's list, such as the
        fixed purchases, have no entry.
    """
    constituents = read_input(path.parent, path.stem)
    return {
        yahoo_symbol(str(symbol)): str(name)
        for symbol, name in zip(
            constituents["symbol"], constituents["security"], strict=True
        )
    }
