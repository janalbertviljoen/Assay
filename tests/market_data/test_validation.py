"""The stored-table gate ``check_table`` on every stored table (market_data/validation.py)."""

import numpy as np
import pandas as pd
import pytest

from Toolbox.market_data.sources.constituents import CHANGE_COLUMNS, CONSTITUENT_COLUMNS
from Toolbox.market_data.sources.edgar import COMPANYFACTS_COLUMNS
from Toolbox.market_data.sources.fred import OBSERVATION_COLUMNS
from Toolbox.market_data.sources.prices import (
    DIVIDEND_COLUMNS,
    LISTING_COLUMNS,
    PRICE_COLUMNS,
    SPLIT_COLUMNS,
)
from Toolbox.market_data.update import TABLE_SCHEMAS
from Toolbox.market_data.validation import check_table
from Toolbox.skatkis.pipelines.validation import SchemaValidationError

FACTS_COLUMNS = COMPANYFACTS_COLUMNS | {"snapshot_as_of": "datetime64[ns]"}

DTYPES: dict[str, dict[str, str]] = {
    "facts": FACTS_COLUMNS,
    "prices": PRICE_COLUMNS,
    "dividends": DIVIDEND_COLUMNS,
    "splits": SPLIT_COLUMNS,
    "listings": LISTING_COLUMNS,
    "constituents": CONSTITUENT_COLUMNS,
    "changes": CHANGE_COLUMNS,
    "observations": OBSERVATION_COLUMNS,
}


def _fact(accession: str, period_start: str | None, value: float) -> dict[str, object]:
    """One fact of AAA (CIK 1): net income for a year, or an instant if no start."""
    return {
        "cik": 1,
        "entity_name": "AAA Inc.",
        "field": "net_income",
        "taxonomy": "us-gaap",
        "tag": "NetIncomeLoss",
        "tag_priority": 0,
        "unit": "USD",
        "value": value,
        "period_start": pd.Timestamp(period_start) if period_start else pd.NaT,
        "period_end": pd.Timestamp("2019-12-31"),
        "fiscal_year": 2019,
        "fiscal_period": "FY",
        "form": "10-K",
        "filed": pd.Timestamp("2020-02-14"),
        "accession": accession,
        "frame": None,
        "snapshot_as_of": pd.Timestamp("2020-06-30"),
    }


def _clean(name: str) -> pd.DataFrame:
    """A small table ``name`` that meets its schema, in the dtypes its parser writes."""
    day = pd.Timestamp("2020-03-20")
    rows: dict[str, list[object]]
    if name == "facts":
        frame = pd.DataFrame(
            [
                _fact("A1", "2019-01-01", 5.0),
                _fact("A1", None, 6.0),  # an instant: no period_start
                _fact("A2", "2019-01-01", 5.0),  # the same value again in a 10-K/A
            ]
        )
        return frame.astype(FACTS_COLUMNS)
    if name == "prices":
        rows = {
            "symbol": ["AAA", "AAA", "BBB"],
            "date": [day, day + pd.Timedelta(days=1), day],
            "open": [10.0, np.nan, 20.0],  # a day without a trade keeps its row
            "high": [11.0, np.nan, 21.0],
            "low": [9.0, np.nan, 19.0],
            "close": [10.5, np.nan, 20.5],
            "adj_close": [10.4, np.nan, 20.1],
            "volume": [0.0, np.nan, 100.0],
            "currency": ["USD", "USD", "USD"],
        }
    elif name == "dividends":
        rows = {
            "symbol": ["AAA", "BBB"],
            "ex_date": [day, day],
            "amount": [0.25, 0.5],
            "currency": ["USD", "USD"],
        }
    elif name == "splits":
        rows = {
            "symbol": ["AAA"],
            "date": [day],
            "numerator": [2.0],
            "denominator": [1.0],
        }
    elif name == "listings":
        rows = {"symbol": ["AAA", "BBB"], "first_date": [day, day]}
    elif name == "constituents":
        rows = {
            "symbol": ["AAA", "BBB.B"],
            "security": ["AAA Inc.", "BBB Corp."],
            "gics_sector": ["Energy", "Utilities"],
            "gics_sub_industry": ["Oil", "Electric"],
            "date_added": [day, pd.NaT],
            "cik": [1, None],
        }
    elif name == "changes":
        rows = {
            "date": [day, day],  # one date may carry several changes
            "added_symbol": ["AAA", None],
            "added_security": ["AAA Inc.", None],
            "removed_symbol": [None, "CCC"],
            "removed_security": [None, "CCC Ltd."],
            "reason": ["", "acquired"],
        }
    else:
        rows = {
            "series_id": ["DEXSFUS", "DEXSFUS"],
            "date": [day, day + pd.Timedelta(days=1)],
            "value": [18.5, np.nan],  # a holiday keeps its row
        }
    return pd.DataFrame(rows).astype(DTYPES[name])


def _empty(name: str) -> pd.DataFrame:
    """The table ``name`` with its columns and dtypes and no rows."""
    columns = DTYPES[name]
    return pd.DataFrame(columns=list(columns)).astype(columns)


def _rejects(table: pd.DataFrame, name: str, text: str) -> None:
    """Assert that ``table`` fails the gate of ``name`` with ``text`` in the message."""
    with pytest.raises(SchemaValidationError) as caught:
        check_table(table, TABLE_SCHEMAS[name], f"test/{name}")
    assert text in str(caught.value)


# ---------------------------------------------------------------------------
# Clean, empty and column checks, for every stored table
# ---------------------------------------------------------------------------


def test_every_stored_table_is_covered() -> None:
    assert set(DTYPES) == set(TABLE_SCHEMAS)
    for name, schema in TABLE_SCHEMAS.items():
        assert list(schema) == list(DTYPES[name]), name


@pytest.mark.parametrize("name", list(TABLE_SCHEMAS))
def test_a_clean_table_passes(name: str) -> None:
    check_table(_clean(name), TABLE_SCHEMAS[name], name)


@pytest.mark.parametrize("name", list(TABLE_SCHEMAS))
def test_an_empty_table_passes(name: str) -> None:
    check_table(_empty(name), TABLE_SCHEMAS[name], name)


@pytest.mark.parametrize("name", list(TABLE_SCHEMAS))
def test_an_extra_column_is_rejected_before_the_constraints(name: str) -> None:
    table = _clean(name).assign(extra=1.0)
    with pytest.raises(ValueError, match="Undeclared columns: \\['extra'\\]") as caught:
        check_table(table, TABLE_SCHEMAS[name], name)
    assert not isinstance(caught.value, SchemaValidationError)


@pytest.mark.parametrize("name", list(TABLE_SCHEMAS))
def test_a_missing_column_is_rejected_before_the_constraints(name: str) -> None:
    dropped = list(DTYPES[name])[-1]
    table = _clean(name).drop(columns=[dropped])
    with pytest.raises(ValueError, match="Missing required columns") as caught:
        check_table(table, TABLE_SCHEMAS[name], name)
    assert not isinstance(caught.value, SchemaValidationError)
    assert dropped in str(caught.value)


def test_a_missing_column_that_may_be_null_is_still_rejected() -> None:
    # frame and fiscal_period carry no tag in the facts schema.
    table = _clean("facts").drop(columns=["frame"])
    with pytest.raises(ValueError, match="Missing required columns: \\['frame'\\]"):
        check_table(table, TABLE_SCHEMAS["facts"], "facts")


def test_the_context_names_the_table() -> None:
    table = _clean("prices")
    table.loc[0, "close"] = 0.0
    with pytest.raises(SchemaValidationError) as caught:
        check_table(table, TABLE_SCHEMAS["prices"], "yahoo/prices")
    assert caught.value.context == "yahoo/prices"
    assert str(caught.value).startswith("[yahoo/prices]")


def test_the_table_is_not_modified() -> None:
    table = _clean("prices")
    table.loc[0, "close"] = 0.0
    before = table.copy()
    with pytest.raises(SchemaValidationError):
        check_table(table, TABLE_SCHEMAS["prices"], "prices")
    pd.testing.assert_frame_equal(table, before)


# ---------------------------------------------------------------------------
# Duplicate keys
# ---------------------------------------------------------------------------


def test_a_duplicate_instant_fact_is_rejected() -> None:
    # Same company, filing, field, tag, unit and period end; period_start missing twice.
    facts = _clean("facts")
    table = pd.concat([facts, facts.iloc[[1]]], ignore_index=True)
    _rejects(table, "facts", "Duplicate rows on key")


def test_a_duration_and_an_instant_with_one_end_are_two_facts() -> None:
    facts = _clean("facts")
    assert facts.loc[0, "accession"] == facts.loc[1, "accession"]
    check_table(facts, TABLE_SCHEMAS["facts"], "facts")


def test_the_facts_key_is_the_documented_one() -> None:
    key = [c for c, m in TABLE_SCHEMAS["facts"].items() if m.get("unique_key")]
    assert key == [
        "cik",
        "field",
        "tag",
        "unit",
        "period_start",
        "period_end",
        "accession",
    ]


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("prices", ["symbol", "date"]),
        ("dividends", ["symbol", "ex_date"]),
        ("splits", ["symbol", "date"]),
        ("listings", ["symbol"]),
        ("constituents", ["symbol"]),
        ("observations", ["series_id", "date"]),
    ],
)
def test_a_duplicate_key_is_rejected(name: str, key: list[str]) -> None:
    declared = [c for c, m in TABLE_SCHEMAS[name].items() if m.get("unique_key")]
    assert declared == key
    table = _clean(name)
    repeated = pd.concat([table, table.iloc[[0]]], ignore_index=True)
    _rejects(repeated, name, f"Duplicate rows on key {key}")


def test_the_changes_table_has_no_key() -> None:
    assert not any(m.get("unique_key") for m in TABLE_SCHEMAS["changes"].values())
    table = _clean("changes")
    check_table(
        pd.concat([table, table], ignore_index=True), TABLE_SCHEMAS["changes"], "c"
    )


def test_the_same_symbol_in_two_tables_does_not_clash() -> None:
    # AAA and BBB on the same day: different keys.
    table = _clean("prices")
    assert (table["date"] == table.loc[0, "date"]).sum() == 2
    check_table(table, TABLE_SCHEMAS["prices"], "prices")


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("column", ["open", "high", "low", "close", "adj_close"])
def test_a_price_of_zero_is_rejected(column: str) -> None:
    table = _clean("prices")
    table.loc[0, column] = 0.0
    _rejects(table, "prices", f"'{column}' must be > 0")


def test_a_volume_of_zero_passes_and_a_negative_one_fails() -> None:
    table = _clean("prices")
    table.loc[2, "volume"] = 0.0
    check_table(table, TABLE_SCHEMAS["prices"], "prices")
    table.loc[2, "volume"] = -1.0
    _rejects(table, "prices", "'volume' must be >= 0")


@pytest.mark.parametrize("name", ["prices", "dividends"])
def test_a_price_not_in_usd_is_rejected(name: str) -> None:
    table = _clean(name)
    table.loc[0, "currency"] = "EUR"
    _rejects(table, name, "Disallowed values detected in 'currency': ['EUR']")


def test_a_dividend_of_zero_is_rejected() -> None:
    table = _clean("dividends")
    table.loc[0, "amount"] = 0.0
    _rejects(table, "dividends", "'amount' must be > 0")


@pytest.mark.parametrize("column", ["numerator", "denominator"])
def test_a_split_ratio_part_of_zero_is_rejected(column: str) -> None:
    table = _clean("splits")
    table.loc[0, column] = 0.0
    _rejects(table, "splits", f"'{column}' must be > 0")


def test_a_member_without_a_sector_is_rejected() -> None:
    table = _clean("constituents")
    table.loc[1, "gics_sector"] = None
    _rejects(table, "constituents", "Null values found in 'gics_sector'")


def test_a_member_may_lack_a_cik_and_a_join_date() -> None:
    table = _clean("constituents")
    assert table["cik"].isna().any() and table["date_added"].isna().any()
    check_table(table, TABLE_SCHEMAS["constituents"], "constituents")


def test_a_change_without_a_date_is_rejected() -> None:
    table = _clean("changes")
    table.loc[0, "date"] = pd.NaT
    _rejects(table, "changes", "Null values found in 'date'")


def test_a_listing_without_a_first_date_is_rejected() -> None:
    table = _clean("listings")
    table.loc[0, "first_date"] = pd.NaT
    _rejects(table, "listings", "Null values found in 'first_date'")


def test_an_observation_may_be_negative_or_missing() -> None:
    table = _clean("observations")
    table.loc[0, "value"] = -3.0
    check_table(table, TABLE_SCHEMAS["observations"], "observations")


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("tag", "MadeUpTag"),
        ("field", "made_up_field"),
        ("taxonomy", "ifrs-full"),
        ("unit", "EUR"),
    ],
)
def test_a_fact_outside_the_tag_map_is_rejected(column: str, value: str) -> None:
    table = _clean("facts")
    table.loc[0, column] = value
    _rejects(table, "facts", f"Disallowed values detected in '{column}': ['{value}']")


def test_a_fact_without_its_snapshot_date_is_rejected() -> None:
    table = _clean("facts")
    table.loc[2, "snapshot_as_of"] = pd.NaT
    _rejects(table, "facts", "Null values found in 'snapshot_as_of'")


@pytest.mark.parametrize("column", ["value", "filed", "form", "period_end"])
def test_a_fact_without_a_required_value_is_rejected(column: str) -> None:
    table = _clean("facts")
    table.loc[0, column] = None
    _rejects(table, "facts", f"Null values found in '{column}'")


def test_a_fact_with_cik_zero_is_rejected() -> None:
    table = _clean("facts")
    table["cik"] = 0
    _rejects(table, "facts", "'cik' must be > 0")
