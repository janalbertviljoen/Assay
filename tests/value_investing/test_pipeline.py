"""The buyability pipeline's gate and soft-expectation report (value_investing/pipeline.py).

A two-company fixture on one rebalance date (2020-03-20), with G2a as the only rule:
AAA reports a negative share count, so its ``market_cap`` and ``pb`` are negative.
"""

from typing import Any

import pandas as pd
import pytest

from Toolbox.skatkis.pipelines.validation import SchemaValidationError
from Toolbox.value_investing.inputs import Tables
from Toolbox.value_investing.pipeline import Buyability, buyability

END = pd.Timestamp("2020-06-30")
BENCHMARK = "^SP500TR"
TAGS = {
    "current_assets": ("us-gaap", "AssetsCurrent", "USD"),
    "current_liabilities": ("us-gaap", "LiabilitiesCurrent", "USD"),
    "stockholders_equity": ("us-gaap", "StockholdersEquity", "USD"),
    "shares_outstanding": ("dei", "EntityCommonStockSharesOutstanding", "shares"),
}
CONFIG: dict[str, Any] = {
    "schedule": {
        "start": "2020-01-01",
        "months": [3],
        "history_years": 3,
        "year_tolerance_days": 45,
        "stale_days": 550,
    },
    "valuation": {"average_years": 3},
    "score": {"min_available": 1, "min_companies": 20, "buckets": 6},
    "learning": {"months": 12, "window": 12},
    "rules": {"G2a": {"min_current_ratio": 2.0}},
}


def _fact(cik: int, field: str, value: float) -> dict[str, object]:
    taxonomy, tag, unit = TAGS[field]
    return {
        "cik": cik,
        "entity_name": f"Company {cik}",
        "field": field,
        "taxonomy": taxonomy,
        "tag": tag,
        "tag_priority": 0,
        "unit": unit,
        "value": value,
        "period_start": pd.NaT,
        "period_end": pd.Timestamp("2019-12-31"),
        "fiscal_year": 2019,
        "fiscal_period": "FY",
        "form": "10-K",
        "filed": pd.Timestamp("2020-02-14"),
        "accession": f"A{cik}",
        "frame": None,
        "snapshot_as_of": END,
    }


def _tables(*, aaa_shares: float, aaa_sector: str | None = "Energy") -> Tables:
    rows = []
    for cik, shares in ((1, aaa_shares), (2, 1000.0)):
        rows += [
            _fact(cik, "current_assets", 300.0),
            _fact(cik, "current_liabilities", 100.0),
            _fact(cik, "stockholders_equity", 500.0),
            _fact(cik, "shares_outstanding", shares),
        ]
    days = pd.bdate_range("2020-01-01", END)
    prices = pd.concat(
        [
            pd.DataFrame({"symbol": s, "date": days, "close": 10.0, "adj_close": 10.0})
            for s in ("AAA", "BBB", BENCHMARK)
        ],
        ignore_index=True,
    )
    universe = pd.DataFrame(
        {
            "symbol": pd.Series(["AAA", "BBB"], dtype="string"),
            "cik": [1, 2],
            "gics_sector": [aaa_sector, "Utilities"],
            "date_added": pd.to_datetime(["2000-01-01"] * 2),
        }
    )
    return Tables(
        facts=pd.DataFrame(rows),
        prices=prices,
        dividends=pd.DataFrame(columns=["symbol", "ex_date", "amount"]),
        splits=pd.DataFrame(
            {
                "symbol": pd.Series([], dtype="string"),
                "date": pd.Series([], dtype="datetime64[ns]"),
                "numerator": pd.Series([], dtype="float64"),
                "denominator": pd.Series([], dtype="float64"),
            }
        ),
        listings=pd.DataFrame(
            {"symbol": ["AAA", "BBB"], "first_date": pd.to_datetime(["2000-01-01"] * 2)}
        ),
        universe=universe,
    )


def _run(tables: Tables) -> Buyability:
    return buyability(tables, CONFIG, end=END, view="on_date", benchmark=BENCHMARK)


@pytest.mark.filterwarnings("ignore:invalid value encountered:RuntimeWarning")
def test_negative_share_count_ratios_are_reported_not_raised() -> None:
    result = _run(_tables(aaa_shares=-1000.0))
    table = result.table.set_index("symbol")
    assert table.loc["AAA", "market_cap"] == -10_000.0
    assert table.loc["AAA", "pb"] == -20.0
    notices = result.report.by_context("buyability:expect_non_negative")
    assert len(notices) == 1
    assert notices[0].category == "unexpected"
    assert notices[0].message == (
        "2 row(s) breach 'expect_non_negative' on ['market_cap', 'pb']"
    )


@pytest.mark.filterwarnings("ignore:invalid value encountered:RuntimeWarning")
def test_a_clean_run_has_no_notices() -> None:
    result = _run(_tables(aaa_shares=1000.0))
    assert result.report.notices == []
    assert result.table["symbol"].tolist() == ["AAA", "BBB"]


@pytest.mark.filterwarnings("ignore:invalid value encountered:RuntimeWarning")
def test_the_output_gate_raises_on_a_member_without_a_sector() -> None:
    with pytest.raises(
        SchemaValidationError, match="Null values found in 'gics_sector'"
    ):
        _run(_tables(aaa_shares=1000.0, aaa_sector=None))
