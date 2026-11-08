"""The update's gates: per-item failures and check-all-before-write (market_data/update.py).

No network: the providers get an ``ApiClient`` whose transport serves fixed payloads, and
snapshots and tables go to ``tmp_path``.
"""

import json
from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from Toolbox.market_data import update as update_module
from Toolbox.market_data.sources.edgar import EdgarCompanyFacts
from Toolbox.market_data.sources.prices import ChartTables, YahooChart
from Toolbox.market_data.update import (
    Storage,
    UpdateResult,
    update_edgar,
    update_prices,
)
from Toolbox.skatkis.io.api import ApiClient, HttpResponse
from Toolbox.skatkis.io.snapshots import SnapshotStore
from Toolbox.skatkis.io.tables import read_table
from Toolbox.skatkis.pipelines.validation import SchemaValidationError

AS_OF = date(2020, 3, 31)
DAY = 86_400
FIRST = 1_584_316_800  # 2020-03-16 00:00 UTC


# ---------------------------------------------------------------------------
# Payloads and a transport that serves them
# ---------------------------------------------------------------------------


def _chart(symbol: str, closes: list[float], currency: str = "USD") -> bytes:
    """A chart payload of daily bars from 2020-03-16 with one dividend."""
    stamps = [FIRST + i * DAY for i in range(len(closes))]
    result: dict[str, Any] = {
        "meta": {"symbol": symbol, "currency": currency, "gmtoffset": 0},
        "timestamp": stamps,
        "indicators": {
            "quote": [
                {
                    "open": closes,
                    "high": closes,
                    "low": closes,
                    "close": closes,
                    "volume": [100.0] * len(closes),
                }
            ],
            "adjclose": [{"adjclose": closes}],
        },
        "events": {"dividends": {str(FIRST): {"date": FIRST, "amount": 0.25}}},
    }
    return json.dumps({"chart": {"result": [result], "error": None}}).encode()


def _transport(
    route: Callable[[str], bytes | None],
) -> Callable[[str, Mapping[str, str], float], HttpResponse]:
    """Return a transport answering 200 with ``route(url)``, or 404 when it is None."""

    def transport(url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse:
        body = route(url)
        return (
            HttpResponse(status=404, body=b"")
            if body is None
            else HttpResponse(200, body)
        )

    return transport


def _client(route: Callable[[str], bytes | None]) -> ApiClient:
    return ApiClient(
        headers={},
        max_requests_per_second=1e9,
        max_retries=0,
        transport=_transport(route),
        sleep=lambda _: None,
    )


def _charts(payloads: Mapping[str, bytes]) -> tuple[YahooChart, YahooChart]:
    """Daily and monthly providers serving ``payloads`` by symbol."""

    def route(url: str) -> bytes | None:
        symbol = url.split("/chart/", maxsplit=1)[1].split("?", maxsplit=1)[0]
        return payloads.get(symbol)

    client = _client(route)
    return (
        YahooChart(client=client, start=date(2020, 1, 1), interval="1d"),
        YahooChart(client=client, start=date(2000, 1, 1), interval="1mo"),
    )


def _storage(tmp_path: Path) -> Storage:
    return Storage(
        snapshots=SnapshotStore(tmp_path / "raw"), interim=tmp_path / "interim"
    )


def _prices(
    tmp_path: Path, tickers: list[str], payloads: Mapping[str, bytes]
) -> UpdateResult:
    daily, monthly = _charts(payloads)
    return update_prices(
        tickers, as_of=AS_OF, storage=_storage(tmp_path), daily=daily, monthly=monthly
    )


def _folder_bytes(folder: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(folder.iterdir())}


GOOD = {"AAA": _chart("AAA", [10.0, 11.0]), "BBB": _chart("BBB", [20.0, 21.0])}


# ---------------------------------------------------------------------------
# update_prices
# ---------------------------------------------------------------------------


def test_clean_symbols_are_all_written(tmp_path: Path) -> None:
    result = _prices(tmp_path, ["AAA", "BBB"], GOOD)
    assert result.failed == {}
    assert result.fetched == ("AAA", "BBB")
    assert result.tables == {"prices": 4, "dividends": 2, "splits": 0, "listings": 2}
    prices = read_table(result.folder / "prices.parquet")
    assert sorted(set(prices["symbol"])) == ["AAA", "BBB"]
    assert {p.name for p in result.folder.glob("*.parquet")} == {
        "prices.parquet",
        "dividends.parquet",
        "splits.parquet",
        "listings.parquet",
    }


def test_a_symbol_with_a_close_of_zero_fails_and_the_others_are_written(
    tmp_path: Path,
) -> None:
    payloads = dict(GOOD) | {"BBB": _chart("BBB", [20.0, 0.0])}
    result = _prices(tmp_path, ["AAA", "BBB"], payloads)
    assert list(result.failed) == ["BBB"]
    assert "prices of BBB" in result.failed["BBB"]
    assert "must be > 0" in result.failed["BBB"]
    assert result.fetched == ("AAA",)
    prices = read_table(result.folder / "prices.parquet")
    assert set(prices["symbol"]) == {"AAA"}
    assert set(read_table(result.folder / "listings.parquet")["symbol"]) == {"AAA"}


def test_a_symbol_priced_in_another_currency_fails(tmp_path: Path) -> None:
    payloads = dict(GOOD) | {"AAA": _chart("AAA", [10.0], currency="EUR")}
    result = _prices(tmp_path, ["AAA", "BBB"], payloads)
    assert list(result.failed) == ["AAA"]
    assert "EUR" in result.failed["AAA"]
    assert result.fetched == ("BBB",)


def test_a_fetch_failure_is_listed_and_the_others_are_written(tmp_path: Path) -> None:
    result = _prices(tmp_path, ["AAA", "CCC"], GOOD)
    assert list(result.failed) == ["CCC"]
    assert "HTTP 404" in result.failed["CCC"]
    assert result.fetched == ("AAA",)
    assert result.tables["prices"] == 2


def test_a_symbol_with_an_extra_column_fails_and_the_others_are_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = update_module.load_chart

    def load_chart(tickers: list[str], **kwargs: Any) -> ChartTables:
        tables = real(tickers, **kwargs)
        if list(tickers) == ["BBB"]:
            return ChartTables(
                prices=tables.prices.assign(extra=1.0),
                dividends=tables.dividends,
                splits=tables.splits,
            )
        return tables

    monkeypatch.setattr(update_module, "load_chart", load_chart)
    result = _prices(tmp_path, ["AAA", "BBB"], GOOD)
    assert list(result.failed) == ["BBB"]
    assert "Undeclared columns: ['extra']" in result.failed["BBB"]
    assert result.fetched == ("AAA",)
    assert set(read_table(result.folder / "prices.parquet")["symbol"]) == {"AAA"}


def test_a_failed_symbol_is_neither_fetched_nor_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # First run stores both snapshots on AS_OF; the second reuses them.
    _prices(tmp_path, ["AAA", "BBB"], GOOD)
    real = update_module.load_chart

    def load_chart(tickers: list[str], **kwargs: Any) -> ChartTables:
        tables = real(tickers, **kwargs)
        if list(tickers) == ["AAA"]:
            return ChartTables(
                prices=tables.prices.drop(columns=["volume"]),
                dividends=tables.dividends,
                splits=tables.splits,
            )
        return tables

    monkeypatch.setattr(update_module, "load_chart", load_chart)
    result = _prices(tmp_path, ["AAA", "BBB"], {})
    assert list(result.failed) == ["AAA"]
    assert "Missing required columns: ['volume']" in result.failed["AAA"]
    assert result.reused == ("BBB",)
    assert result.fetched == ()


def test_the_same_symbol_twice_fails_the_combined_check_and_writes_nothing(
    tmp_path: Path,
) -> None:
    first = _prices(tmp_path, ["AAA", "BBB"], GOOD)
    before = _folder_bytes(first.folder)
    with pytest.raises(SchemaValidationError, match="Duplicate rows on key"):
        _prices(tmp_path, ["AAA", "AAA"], GOOD)
    assert _folder_bytes(first.folder) == before


def test_a_failed_combined_check_leaves_a_new_folder_empty(tmp_path: Path) -> None:
    with pytest.raises(SchemaValidationError):
        _prices(tmp_path, ["AAA", "AAA"], GOOD)
    folder = _storage(tmp_path).folder("yahoo", AS_OF)
    assert not folder.exists() or list(folder.iterdir()) == []


def test_no_symbols_write_empty_tables(tmp_path: Path) -> None:
    result = _prices(tmp_path, [], GOOD)
    assert result.tables == {"prices": 0, "dividends": 0, "splits": 0, "listings": 0}
    assert read_table(result.folder / "listings.parquet").empty


def test_every_symbol_failing_writes_empty_tables(tmp_path: Path) -> None:
    payloads = {"AAA": _chart("AAA", [0.0])}
    result = _prices(tmp_path, ["AAA"], payloads)
    assert list(result.failed) == ["AAA"]
    assert result.tables["prices"] == 0


# ---------------------------------------------------------------------------
# update_edgar
# ---------------------------------------------------------------------------


def _fact(end: str, value: float, accession: str) -> dict[str, Any]:
    return {
        "end": end,
        "val": value,
        "accn": accession,
        "fy": int(end[:4]),
        "fp": "FY",
        "form": "10-K",
        "filed": "2020-02-14",
    }


def _companyfacts(cik: int, assets: list[dict[str, Any]]) -> bytes:
    """A companyfacts payload with the given ``AssetsCurrent`` instants."""
    return json.dumps(
        {
            "cik": cik,
            "entityName": f"Company {cik}",
            "facts": {"us-gaap": {"AssetsCurrent": {"units": {"USD": assets}}}},
        }
    ).encode()


SUBMISSIONS = json.dumps(
    {"filings": {"recent": {"form": ["10-K"], "filingDate": ["2020-02-14"]}}}
).encode()


def _edgar(tmp_path: Path, payloads: Mapping[str, bytes]) -> UpdateResult:
    def route(url: str) -> bytes | None:
        cik = url.split("CIK", maxsplit=1)[1].split(".json", maxsplit=1)[0]
        if "submissions" in url:
            return SUBMISSIONS
        return payloads.get(cik)

    return update_edgar(
        [1, 2], as_of=AS_OF, storage=_storage(tmp_path), client=_client(route)
    )


def test_a_company_with_a_duplicate_fact_fails_and_the_other_is_written(
    tmp_path: Path,
) -> None:
    fact = _fact("2019-12-31", 300.0, "0000000002-20-000001")
    payloads = {
        "0000000001": _companyfacts(1, [_fact("2019-12-31", 100.0, "A1")]),
        "0000000002": _companyfacts(2, [fact, fact]),  # one instant twice
    }
    result = _edgar(tmp_path, payloads)
    assert list(result.failed) == ["0000000002"]
    assert "facts of CIK 0000000002" in result.failed["0000000002"]
    assert "Duplicate rows on key" in result.failed["0000000002"]
    assert result.fetched == ("0000000001",)
    facts = read_table(result.folder / "facts.parquet")
    assert set(facts["cik"]) == {1}
    assert facts["snapshot_as_of"].tolist() == [pd.Timestamp(AS_OF)]


def test_a_company_that_does_not_parse_fails_and_the_other_is_written(
    tmp_path: Path,
) -> None:
    bad = _fact("2019-12-31", 1.0, "A2")
    del bad["form"]
    payloads = {
        "0000000001": _companyfacts(1, [_fact("2019-12-31", 100.0, "A1")]),
        "0000000002": _companyfacts(2, [bad]),
    }
    result = _edgar(tmp_path, payloads)
    assert list(result.failed) == ["0000000002"]
    assert "lacks 'form'" in result.failed["0000000002"]
    assert result.tables == {"facts": 1}


def test_every_company_failing_writes_an_empty_facts_table(tmp_path: Path) -> None:
    result = _edgar(tmp_path, {})
    assert sorted(result.failed) == ["0000000001", "0000000002"]
    assert result.fetched == () and result.reused == ()
    facts = read_table(result.folder / "facts.parquet")
    assert facts.empty
    assert "snapshot_as_of" in facts.columns


def test_the_companyfacts_provider_is_the_facts_folder(tmp_path: Path) -> None:
    result = _edgar(
        tmp_path, {"0000000001": _companyfacts(1, [_fact("2019-12-31", 1.0, "A1")])}
    )
    provider = EdgarCompanyFacts(_client(lambda _: None))
    assert result.folder == _storage(tmp_path).folder(provider.name, AS_OF)
