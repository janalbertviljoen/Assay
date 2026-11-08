"""The buyability output gate ``check_buyability`` (value_investing/validation.py)."""

import numpy as np
import pandas as pd
import pytest

from Toolbox.skatkis.pipelines.contracts import Schema
from Toolbox.skatkis.pipelines.validation import SchemaValidationError
from Toolbox.value_investing.schema import buyability_schema, pipeline_schema
from Toolbox.value_investing.validation import check_buyability

BUCKETS = 6


@pytest.fixture
def schema() -> Schema:
    return buyability_schema(pipeline_schema(["G2a", "E1"], buckets=BUCKETS))


def _table() -> pd.DataFrame:
    """Two companies on one date and AAA on a second; E1 not evaluable for BBB."""
    return pd.DataFrame(
        {
            "symbol": pd.Series(["AAA", "AAA", "BBB"], dtype="string"),
            "date": pd.to_datetime(["2020-03-20", "2020-06-19", "2020-03-20"]),
            "gics_sector": ["Energy", "Energy", "Utilities"],
            "close": [10.0, 11.0, 20.0],
            "market_cap": [1e9, 1.1e9, 0.0],
            "average_eps": [1.0, -0.5, np.nan],
            "pe_average": [10.0, np.nan, np.nan],
            "pb": [1.5, 1.6, np.nan],
            "g2a_value": [3.0, 2.0, 1.0],
            "g2a_pass": [1.0, 1.0, 0.0],
            "e1_value": [0.1, 0.2, np.nan],
            "e1_pass": [0.0, 1.0, np.nan],
            "g2a_points": [5.0, 3.0, 0.0],
            "e1_points": [0.0, 5.0, np.nan],
            "score": [0.5, 1.0, 0.0],
            "score_G": [1.0, 1.0, 0.0],
            "score_E": [0.0, 1.0, np.nan],
            "score_binned": [5.0, 8.0, 0.0],
            "score_binned_weighted": [2.5, 4.0, 0.0],
            "score_weighted_share": [0.5, 1.0, 0.0],
            "n_passed": pd.array([1, 2, 0], dtype="Int64"),
            "n_available": pd.array([2, 2, 1], dtype="Int64"),
            "score_ic": [0.3, np.nan, 0.0],
        }
    )


def _rejects(table: pd.DataFrame, schema: Schema, text: str) -> None:
    with pytest.raises(SchemaValidationError) as caught:
        check_buyability(table, schema)
    assert text in str(caught.value)
    assert caught.value.context == "buyability"


def test_a_clean_table_passes(schema: Schema) -> None:
    check_buyability(_table(), schema)


def test_the_column_order_does_not_matter(schema: Schema) -> None:
    table = _table()
    check_buyability(table[list(reversed(table.columns))], schema)


def test_an_extra_column_is_rejected(schema: Schema) -> None:
    with pytest.raises(ValueError, match="Undeclared columns: \\['g3_value'\\]") as e:
        check_buyability(_table().assign(g3_value=1.0), schema)
    assert not isinstance(e.value, SchemaValidationError)


def test_a_missing_column_is_rejected(schema: Schema) -> None:
    with pytest.raises(ValueError, match="Missing required columns: \\['e1_pass'\\]"):
        check_buyability(_table().drop(columns=["e1_pass"]), schema)


def test_a_missing_column_that_may_hold_nulls_is_still_rejected(
    schema: Schema,
) -> None:
    with pytest.raises(ValueError, match="Missing required columns: \\['pb'\\]"):
        check_buyability(_table().drop(columns=["pb"]), schema)


def test_a_flag_of_one_half_is_rejected(schema: Schema) -> None:
    table = _table()
    table.loc[0, "g2a_pass"] = 0.5
    _rejects(table, schema, "Disallowed values detected in 'g2a_pass': ['0.5']")


def test_a_grade_equal_to_buckets_is_rejected(schema: Schema) -> None:
    table = _table()
    table.loc[1, "e1_points"] = float(BUCKETS)
    _rejects(table, schema, "Disallowed values detected in 'e1_points': ['6.0']")


def test_the_top_grade_passes(schema: Schema) -> None:
    table = _table()
    table.loc[1, "e1_points"] = float(BUCKETS - 1)
    check_buyability(table, schema)


def test_a_duplicate_symbol_and_date_is_rejected(schema: Schema) -> None:
    table = pd.concat([_table(), _table().iloc[[2]]], ignore_index=True)
    _rejects(table, schema, "Duplicate rows on key ['symbol', 'date']: 2 rows")


def test_a_duplicate_with_repeated_row_labels_is_rejected(schema: Schema) -> None:
    table = pd.concat([_table(), _table().iloc[[2]]])
    assert not table.index.is_unique
    _rejects(table, schema, "Duplicate rows on key ['symbol', 'date']")


def test_a_negative_close_is_rejected(schema: Schema) -> None:
    table = _table()
    table.loc[0, "close"] = -1.0
    _rejects(table, schema, "'close' must be > 0")


def test_a_missing_close_is_rejected(schema: Schema) -> None:
    table = _table()
    table.loc[0, "close"] = np.nan
    _rejects(table, schema, "Null values found in 'close'")


def test_a_missing_sector_is_rejected(schema: Schema) -> None:
    table = _table()
    table.loc[2, "gics_sector"] = None
    _rejects(table, schema, "Null values found in 'gics_sector'")


def test_a_pe_of_zero_is_rejected(schema: Schema) -> None:
    table = _table()
    table.loc[0, "pe_average"] = 0.0
    _rejects(table, schema, "'pe_average' must be > 0")


def test_a_negative_learned_score_is_rejected(schema: Schema) -> None:
    table = _table()
    table.loc[0, "score_ic"] = -0.1
    _rejects(table, schema, "'score_ic' must be >= 0")


def test_a_share_one_rounding_step_above_1_passes(schema: Schema) -> None:
    table = _table()
    table.loc[1, "score_weighted_share"] = 1 + 2.2e-16
    check_buyability(table, schema)


def test_a_share_above_1_is_rejected(schema: Schema) -> None:
    table = _table()
    table.loc[1, "score_weighted_share"] = 1.01
    _rejects(table, schema, "'score_weighted_share' has values outside [0, 1]")


@pytest.mark.parametrize("column", ["market_cap", "pb"])
def test_a_negative_share_count_ratio_passes_the_gate(
    schema: Schema, column: str
) -> None:
    table = _table()
    table.loc[0, column] = -5.0
    check_buyability(table, schema)


def test_the_table_is_not_modified(schema: Schema) -> None:
    table = _table()
    table.loc[0, "g2a_pass"] = 0.5
    before = table.copy()
    with pytest.raises(SchemaValidationError):
        check_buyability(table, schema)
    pd.testing.assert_frame_equal(table, before)
