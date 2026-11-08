"""Notices, the pipeline report and the soft-expectation scan (skatkis/pipelines/report.py)."""

import numpy as np
import pandas as pd
import pytest

from Toolbox.skatkis.pipelines.contracts import Schema
from Toolbox.skatkis.pipelines.report import (
    SOFT_EXPECTATIONS,
    Notice,
    PipelineReport,
    expectation_notices,
    soft_violations,
)
from Toolbox.skatkis.pipelines.schema import (
    expect_non_negative,
    expect_positive,
    expect_probability,
    expect_value,
    type_float,
)

GRAIN = ("symbol", "date")


def _table(column: str, values: list[float]) -> pd.DataFrame:
    """One value per company AAA, BBB, ... on one date."""
    symbols = ["AAA", "BBB", "CCC", "DDD", "EEE"][: len(values)]
    return pd.DataFrame(
        {
            "symbol": symbols,
            "date": pd.Timestamp("2020-03-20"),
            column: values,
        }
    )


# ---------------------------------------------------------------------------
# Each soft expectation, with its boundary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("flag", "values", "breached"),
    [
        (expect_value, [1.0, np.nan, 0.0], ["BBB"]),
        (expect_non_negative, [0.0, -1e-13, -1e-11, -5.0, np.nan], ["CCC", "DDD"]),
        (expect_positive, [1e-300, 0.0, -1.0, np.nan], ["BBB", "CCC"]),
        (
            expect_probability,
            [0.0, 1.0, 1 + 1e-13, 1 + 1e-11, -1e-11],
            ["DDD", "EEE"],
        ),
    ],
)
def test_each_flag_marks_its_breaches(
    flag: dict[str, bool], values: list[float], breached: list[str]
) -> None:
    df = _table("x", values)
    rows = soft_violations(df, {"x": type_float | flag}, context="t", grain=GRAIN)
    name = next(iter(flag))
    assert rows["symbol"].tolist() == breached
    assert (rows["flag"] == name).all()
    assert (rows["column"] == "x").all()
    assert (rows["context"] == "t").all()
    assert list(rows.columns) == ["context", "flag", "column", "value", *GRAIN]


def test_the_breaching_values_are_kept() -> None:
    df = _table("market_cap", [10.0, -3.0])
    rows = soft_violations(
        df, {"market_cap": dict(expect_non_negative)}, context="t", grain=GRAIN
    )
    assert rows["value"].tolist() == [-3.0]
    assert rows["date"].tolist() == [pd.Timestamp("2020-03-20")]


def test_the_flags_cover_the_four_expectations() -> None:
    assert list(SOFT_EXPECTATIONS) == [
        "expect_value",
        "expect_non_negative",
        "expect_positive",
        "expect_probability",
    ]


def test_rows_are_ordered_by_flag_then_column_in_schema_order() -> None:
    df = pd.DataFrame(
        {"symbol": ["AAA", "BBB"], "b": [-1.0, -2.0], "a": [-1.0, np.nan]}
    )
    schema: Schema = {
        "b": expect_non_negative | expect_value,
        "a": expect_non_negative | expect_value,
    }
    rows = soft_violations(df, schema, context="t", grain=["symbol"])
    assert list(zip(rows["flag"], rows["column"], rows["symbol"], strict=True)) == [
        ("expect_value", "a", "BBB"),
        ("expect_non_negative", "b", "AAA"),
        ("expect_non_negative", "b", "BBB"),
        ("expect_non_negative", "a", "AAA"),
    ]


def test_a_tagged_column_absent_from_the_table_is_skipped() -> None:
    df = _table("x", [1.0])
    rows = soft_violations(
        df, {"missing": dict(expect_value)}, context="t", grain=GRAIN
    )
    assert rows.empty


def test_grain_columns_absent_from_the_table_are_left_out() -> None:
    df = pd.DataFrame({"symbol": ["AAA"], "x": [-1.0]})
    rows = soft_violations(
        df, {"x": dict(expect_non_negative)}, context="t", grain=GRAIN
    )
    assert list(rows.columns) == ["context", "flag", "column", "value", "symbol"]


def test_a_clean_table_gives_no_rows_and_no_notices() -> None:
    df = _table("x", [0.0, 0.5, 1.0])
    schema: Schema = {"x": expect_probability | expect_non_negative | expect_value}
    rows = soft_violations(df, schema, context="t", grain=GRAIN)
    assert rows.empty
    assert list(rows.columns) == ["context", "flag", "column", "value", *GRAIN]
    assert expectation_notices(df, schema, context="t", grain=GRAIN) == []


def test_the_scan_does_not_modify_the_table() -> None:
    df = _table("x", [-1.0, np.nan])
    before = df.copy()
    soft_violations(
        df, {"x": expect_non_negative | expect_value}, context="t", grain=GRAIN
    )
    pd.testing.assert_frame_equal(df, before)


# ---------------------------------------------------------------------------
# Notices
# ---------------------------------------------------------------------------


def test_one_notice_per_flag_counts_rows_and_names_columns() -> None:
    df = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB"],
            "market_cap": [-1.0, 5.0],
            "pb": [-2.0, -3.0],
        }
    )
    schema: Schema = {
        "market_cap": dict(expect_non_negative),
        "pb": dict(expect_non_negative),
    }
    notices = expectation_notices(df, schema, context="buyability", grain=["symbol"])
    assert notices == [
        Notice(
            context="buyability:expect_non_negative",
            message="3 row(s) breach 'expect_non_negative' on ['market_cap', 'pb']",
            category="unexpected",
        )
    ]


def test_notices_follow_the_flag_order() -> None:
    df = pd.DataFrame({"x": [np.nan, -1.0]})
    schema: Schema = {"x": expect_non_negative | expect_value}
    notices = expectation_notices(df, schema, context="t", grain=[])
    assert [n.context for n in notices] == ["t:expect_value", "t:expect_non_negative"]


# ---------------------------------------------------------------------------
# PipelineReport
# ---------------------------------------------------------------------------


def _report() -> PipelineReport:
    return PipelineReport(
        notices=[
            Notice("prices", "2 defaults used", "default"),
            Notice("buyability", "1 row(s) breach", "unexpected"),
            Notice("prices", "a note"),
        ]
    )


def test_summary_lists_each_notice() -> None:
    assert _report().summary() == (
        "Pipeline report: 3 notice(s)\n"
        "  [default] prices: 2 defaults used\n"
        "  [unexpected] buyability: 1 row(s) breach\n"
        "  [info] prices: a note"
    )


def test_summary_of_an_empty_report() -> None:
    assert PipelineReport().summary() == "Pipeline report: no notices."


def test_by_category_and_by_context() -> None:
    report = _report()
    assert [n.message for n in report.by_category("default")] == ["2 defaults used"]
    assert [n.message for n in report.by_context("prices")] == [
        "2 defaults used",
        "a note",
    ]
    assert report.by_category("none") == []


def test_to_dataframe_has_one_row_per_notice() -> None:
    table = _report().to_dataframe()
    assert list(table.columns) == ["context", "message", "category"]
    assert table["category"].tolist() == ["default", "unexpected", "info"]


def test_to_dataframe_of_an_empty_report_keeps_its_columns() -> None:
    table = PipelineReport().to_dataframe()
    assert table.empty
    assert list(table.columns) == ["context", "message", "category"]


def test_reports_do_not_share_their_notices() -> None:
    first, second = PipelineReport(), PipelineReport()
    first.notices.append(Notice("a", "b"))
    assert second.notices == []
