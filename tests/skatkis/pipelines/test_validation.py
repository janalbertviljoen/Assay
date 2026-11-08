"""Schema validation on Pandera and the column checks (skatkis/pipelines/validation.py)."""

import numpy as np
import pandas as pd
import pytest

from Toolbox.skatkis.pipelines.contracts import Schema
from Toolbox.skatkis.pipelines.schema import (
    allowed_values,
    non_negative,
    positive,
    probability,
    required,
    required_if,
    type_date,
    type_float,
    type_str,
    unique_key,
)
from Toolbox.skatkis.pipelines.validation import (
    SchemaValidationError,
    assert_exact_columns,
    assert_required_columns,
    validate_from_schema,
)

SCHEMA: Schema = {
    "symbol": type_str | required | unique_key,
    "date": type_date | required | unique_key,
    "kind": dict(type_str),
    "share": type_float | probability,
    "close": type_float | positive,
    "volume": type_float | non_negative,
    "flag": type_float | allowed_values({0.0, 1.0}),
    "note": type_str | required_if("kind", "annual"),
    "count": type_float | required,
}


def _clean() -> pd.DataFrame:
    """Three rows of AAA, BBB and CCC that meet every rule of ``SCHEMA``."""
    return pd.DataFrame(
        {
            "symbol": ["AAA", "BBB", "CCC"],
            "date": pd.to_datetime(["2020-03-20"] * 3),
            "kind": ["annual", "quarter", "annual"],
            "share": [0.0, 0.5, 1.0],
            "close": [10.0, 20.0, np.nan],
            "volume": [0.0, 5.0, np.nan],
            "flag": [0.0, 1.0, np.nan],
            "note": ["a", None, "c"],
            "count": [1.0, 2.0, 3.0],
        }
    )


def _error(df: pd.DataFrame, schema: Schema = SCHEMA) -> SchemaValidationError:
    """Return the error ``validate_from_schema`` raises on ``df``."""
    with pytest.raises(SchemaValidationError) as caught:
        validate_from_schema(df, schema, "ctx")
    return caught.value


# ---------------------------------------------------------------------------
# validate_from_schema: passing tables
# ---------------------------------------------------------------------------


def test_a_clean_table_passes() -> None:
    validate_from_schema(_clean(), SCHEMA, "ctx")


def test_an_empty_table_with_the_columns_passes() -> None:
    validate_from_schema(_clean().iloc[0:0], SCHEMA, "ctx")


def test_an_undeclared_column_is_allowed() -> None:
    validate_from_schema(_clean().assign(extra=-1.0), SCHEMA, "ctx")


def test_nulls_pass_every_value_check() -> None:
    df = _clean()
    for column in ["share", "close", "volume", "flag"]:
        df[column] = np.nan
    validate_from_schema(df, SCHEMA, "ctx")


def test_dtypes_are_not_checked() -> None:
    df = _clean().astype({"count": "int64", "close": "object"})
    validate_from_schema(df, SCHEMA, "ctx")


# ---------------------------------------------------------------------------
# validate_from_schema: every violation in one error
# ---------------------------------------------------------------------------


def test_every_kind_of_violation_is_reported_together() -> None:
    df = _clean()
    df.loc[1, "symbol"] = "AAA"  # duplicate key with row 0
    df.loc[0, "share"] = 1.5  # probability
    df.loc[2, "close"] = 0.0  # positive
    df.loc[2, "volume"] = -1.0  # non-negative
    df.loc[1, "flag"] = 0.5  # allowed values
    df.loc[2, "note"] = None  # required where kind is annual
    df.loc[1, "count"] = np.nan  # required
    error = _error(df)
    text = str(error)
    assert text.startswith("[ctx] 7 schema violation(s):")
    assert "Duplicate rows on key ['symbol', 'date']: 2 rows" in text
    assert "'share' has values outside [0, 1]. Found 1 invalid values" in text
    assert "'close' must be > 0. Found 1 invalid values" in text
    assert "'volume' must be >= 0. Found 1 invalid values" in text
    assert "Disallowed values detected in 'flag': ['0.5']" in text
    assert "Allowed values: [0.0, 1.0]" in text
    assert "Null values found in 'note' where kind == 'annual'" in text
    assert "Null values found in 'count': 1 rows" in text
    assert error.context == "ctx"


def test_sample_rows_are_named_by_their_key_values() -> None:
    df = _clean()
    df.loc[2, "close"] = -5.0
    text = str(_error(df))
    assert "Rows: symbol='CCC', date=Timestamp('2020-03-20 00:00:00')" in text


def test_at_most_five_sample_rows_are_named() -> None:
    df = pd.DataFrame({"symbol": [f"S{i}" for i in range(7)], "close": [0.0] * 7})
    text = str(_error(df, {"symbol": unique_key, "close": positive}))
    assert "Found 7 invalid values" in text
    assert "symbol='S4'" in text
    assert "symbol='S5'" not in text
    assert "(+2 more)" in text


def test_a_missing_required_column_is_named() -> None:
    df = _clean().drop(columns=["count"])
    text = str(_error(df))
    assert "[ctx] Missing required columns: ['count']" in text


def test_a_missing_key_column_fails_its_own_check() -> None:
    df = _clean().drop(columns=["date"])
    text = str(_error(df, {"symbol": unique_key, "date": unique_key}))
    assert "Missing unique-key columns: ['symbol', 'date']" in text


def test_a_missing_column_with_allowed_values_fails_its_own_check() -> None:
    df = _clean().drop(columns=["flag"])
    text = str(_error(df, {"flag": allowed_values({0.0, 1.0})}))
    assert "Missing column with allowed values: ['flag']" in text


def test_required_if_applies_only_where_the_condition_holds() -> None:
    df = _clean()
    df.loc[1, "note"] = None  # kind is quarter: not required
    validate_from_schema(df, SCHEMA, "ctx")


def test_required_if_with_the_column_absent_fails_where_the_condition_holds() -> None:
    df = _clean().drop(columns=["note"])
    schema = {"symbol": unique_key, "note": required_if("kind", "annual")}
    assert "Null values found in 'note' where kind == 'annual'" in str(
        _error(df, schema)
    )


# ---------------------------------------------------------------------------
# validate_from_schema: Pandera failure cases and check names
# ---------------------------------------------------------------------------


def test_failure_cases_hold_pandera_rows() -> None:
    df = _clean()
    df.loc[0, "close"] = 0.0
    cases = _error(df).failure_cases
    assert isinstance(cases, pd.DataFrame)
    assert {"column", "check", "index", "failure_case"} <= set(cases.columns)
    row = cases[cases["column"] == "close"].iloc[0]
    assert row["check"] == "must be > 0"
    assert row["index"] == 0
    assert row["failure_case"] == 0.0


@pytest.mark.parametrize(
    ("schema", "df", "check"),
    [
        (
            {"a": required},
            pd.DataFrame({"b": [1.0]}),
            "column_in_dataframe",
        ),
        (
            {"a": required},
            pd.DataFrame({"a": [np.nan]}),
            "not_nullable",
        ),
        (
            # The key is checked at frame level, so one key column is reported as
            # multiple_fields_uniqueness too; field_uniqueness never arises.
            {"a": unique_key},
            pd.DataFrame({"a": ["AAA", "AAA"]}),
            "multiple_fields_uniqueness",
        ),
        (
            {"a": unique_key, "b": unique_key},
            pd.DataFrame({"a": ["AAA", "AAA"], "b": [1, 1]}),
            "multiple_fields_uniqueness",
        ),
    ],
)
def test_the_pandera_check_names_the_error_text_relies_on(
    schema: Schema, df: pd.DataFrame, check: str
) -> None:
    assert check in set(_error(df, schema).failure_cases["check"])


def test_one_key_column_reports_duplicates_by_that_column() -> None:
    text = str(_error(pd.DataFrame({"a": ["AAA", "AAA"]}), {"a": unique_key}))
    assert "Duplicate rows on key ['a']: 2 rows" in text


# ---------------------------------------------------------------------------
# validate_from_schema: keys, labels and the caller's frame
# ---------------------------------------------------------------------------


def test_missing_values_in_a_key_compare_as_equal() -> None:
    # Two instant facts with no period_start and otherwise the same key.
    df = pd.DataFrame(
        {
            "accession": ["A1", "A1"],
            "period_start": pd.to_datetime([None, None]),
            "period_end": pd.to_datetime(["2019-12-31"] * 2),
        }
    )
    schema = {c: dict(unique_key) for c in df.columns}
    assert "Duplicate rows on key" in str(_error(df, schema))


def test_a_missing_value_and_a_date_in_a_key_differ() -> None:
    df = pd.DataFrame(
        {
            "accession": ["A1", "A1"],
            "period_start": pd.to_datetime([None, "2019-01-01"]),
        }
    )
    validate_from_schema(df, {c: dict(unique_key) for c in df.columns}, "ctx")


def test_repeated_row_labels_are_checked_by_position() -> None:
    df = pd.DataFrame({"close": [1.0, -1.0, 2.0]}, index=[7, 7, 7])
    text = str(_error(df, {"close": positive}))
    assert "Rows: row 1" in text


def test_repeated_row_labels_with_keys_name_the_key_values() -> None:
    df = pd.DataFrame(
        {"symbol": ["AAA", "BBB", "BBB"], "close": [1.0, 2.0, 3.0]}, index=[0, 0, 0]
    )
    text = str(_error(df, {"symbol": unique_key, "close": positive}))
    assert "Duplicate rows on key ['symbol']: 2 rows" in text
    assert "symbol='BBB'" in text


def test_the_callers_frame_is_unchanged() -> None:
    df = _clean().astype({"count": "int64"})
    df.loc[0, "share"] = 2.0
    df.index = pd.Index([5, 5, 6])
    before = df.copy()
    dtypes = df.dtypes.copy()
    with pytest.raises(SchemaValidationError):
        validate_from_schema(df, SCHEMA, "ctx")
    pd.testing.assert_frame_equal(df, before)
    pd.testing.assert_series_equal(df.dtypes, dtypes)
    assert df.index.tolist() == [5, 5, 6]


def test_the_callers_frame_is_unchanged_when_it_passes() -> None:
    df = _clean()
    before = df.copy()
    validate_from_schema(df, SCHEMA, "ctx")
    pd.testing.assert_frame_equal(df, before)


def test_schema_validation_error_is_a_value_error() -> None:
    assert issubclass(SchemaValidationError, ValueError)


# ---------------------------------------------------------------------------
# Bounds and their tolerance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("flag", "value", "passes"),
    [
        (probability, 0.0, True),
        (probability, 1.0, True),
        (probability, 1 + 2.2e-16, True),
        (probability, 1 + 1e-13, True),
        (probability, 1 + 1e-11, False),
        (probability, -1e-13, True),
        (probability, -1e-11, False),
        (non_negative, 0.0, True),
        (non_negative, -1e-13, True),
        (non_negative, -1e-11, False),
        (positive, 1e-300, True),
        (positive, 0.0, False),
        (positive, -1e-13, False),
    ],
)
def test_bound_boundaries(flag: dict[str, bool], value: float, passes: bool) -> None:
    df = pd.DataFrame({"x": [value]})
    if passes:
        validate_from_schema(df, {"x": dict(flag)}, "ctx")
    else:
        _error(df, {"x": dict(flag)})


# ---------------------------------------------------------------------------
# Column assertions
# ---------------------------------------------------------------------------


def test_exact_columns_pass_in_any_order() -> None:
    df = pd.DataFrame({"b": [1], "a": [2]})
    assert_exact_columns(df, ["a", "b"], "ctx")


def test_exact_columns_reject_an_undeclared_column() -> None:
    df = pd.DataFrame({"a": [1], "b": [2], "z": [3]})
    with pytest.raises(ValueError, match="\\[ctx\\] Undeclared columns: \\['z'\\]"):
        assert_exact_columns(df, ["a", "b"], "ctx")


def test_exact_columns_reject_a_missing_column() -> None:
    df = pd.DataFrame({"a": [1]})
    with pytest.raises(ValueError, match="Missing required columns: \\['b'\\]"):
        assert_exact_columns(df, ["a", "b"], "ctx")


def test_exact_columns_on_an_empty_frame_check_the_columns_only() -> None:
    assert_exact_columns(pd.DataFrame(columns=["a", "b"]), ["a", "b"], "ctx")


def test_required_columns_allow_extra_columns() -> None:
    df = pd.DataFrame({"a": [1], "z": [3]})
    assert_required_columns(df, ["a"], "ctx")


def test_required_columns_name_the_missing_and_the_present() -> None:
    df = pd.DataFrame({"a": [1]})
    with pytest.raises(ValueError) as caught:
        assert_required_columns(df, ["a", "b", "c"], "ctx")
    text = str(caught.value)
    assert "[ctx] Missing required columns: ['b', 'c']" in text
    assert "Columns present: ['a']" in text
