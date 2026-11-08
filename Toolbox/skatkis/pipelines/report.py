"""
skatkis/pipelines/report.py
---------------------------
Reporting for pipeline runs: observations that are recorded, never raised.

A ``PipelineReport`` is a flat collection of ``Notice`` entries: assumptions, defaults
and soft-expectation breaches seen in a run, so a run that relied on them is visible
and never indistinguishable from one that did not. The caller collects the notices
(for example from ``expectation_notices``); this module knows nothing about what a
check inspects. Hard failures belong to ``skatkis.pipelines.validation``.

The one generic check is the soft expectation: a column tagged ``expect_value``,
``expect_non_negative``, ``expect_positive`` or ``expect_probability`` in a schema is
scanned, and each breach becomes a row of ``soft_violations`` and, summarised, a
``Notice``.

Owns
----
``Notice``, ``PipelineReport`` and the soft-expectation scan.

Must not
--------
Raise on data or block a run (``skatkis.pipelines.validation``); hold domain checks
(the tool's own checks); print or write files (callers print ``summary``).

Public API
----------
Notice(context, message, category)
    One observation.
PipelineReport(notices)
    The run's notices, with ``summary``, ``by_category``, ``by_context`` and
    ``to_dataframe``.
soft_violations(df, schema, *, context, grain)
    One row per breached soft expectation, with the table's grain columns.
expectation_notices(df, schema, *, context, grain)
    One notice per soft expectation breached in the table.
SOFT_EXPECTATIONS
    The expectation flags and the test each applies.

Dependency rule
---------------
pandas, the standard library, ``skatkis.pipelines.contracts`` (the ``Schema``
type) and ``skatkis.pipelines.schema`` (``BOUND_TOLERANCE``). No tool imports.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import pandas as pd

from Toolbox.skatkis.pipelines.contracts import Schema
from Toolbox.skatkis.pipelines.schema import BOUND_TOLERANCE


@dataclass(frozen=True)
class Notice:
    """
    One reportable observation about a pipeline run.

    Parameters
    ----------
    context : str
        Where the notice came from: the table, layer or check, not free text.
    message : str
        What was observed, in plain words.
    category : str, default "info"
        Open classification (``"default"``, ``"unexpected"``, ...), kept free until
        the categories that recur across tools are known.
    """

    context: str
    message: str
    category: str = "info"


@dataclass
class PipelineReport:
    """The notices of one run."""

    notices: list[Notice] = field(default_factory=list[Notice])

    def summary(self) -> str:
        """Return the notices as plain text, one line each, for the caller to print."""
        if not self.notices:
            return "Pipeline report: no notices."
        lines = [f"Pipeline report: {len(self.notices)} notice(s)"]
        lines += [f"  [{n.category}] {n.context}: {n.message}" for n in self.notices]
        return "\n".join(lines)

    def by_category(self, category: str) -> list[Notice]:
        """Return the notices of ``category``."""
        return [n for n in self.notices if n.category == category]

    def by_context(self, context: str) -> list[Notice]:
        """Return the notices from ``context``."""
        return [n for n in self.notices if n.context == context]

    def to_dataframe(self) -> pd.DataFrame:
        """
        Return the notices as a table with columns ``context``, ``message``, ``category``.

        A clean run gives the columns with no rows, so a table written from it still
        shows that the checks ran.
        """
        return pd.DataFrame(
            [(n.context, n.message, n.category) for n in self.notices],
            columns=["context", "message", "category"],
        )


# ---------------------------------------------------------------------------
# Soft expectations
# ---------------------------------------------------------------------------


def _missing(values: pd.Series) -> pd.Series:
    """Mark a missing value."""
    return values.isna()


def _negative(values: pd.Series) -> pd.Series:
    """Mark a value below zero, beyond ``BOUND_TOLERANCE``; missing passes."""
    return values < -BOUND_TOLERANCE


def _not_positive(values: pd.Series) -> pd.Series:
    """Mark a value of zero or below; missing passes."""
    return values <= 0


def _outside_unit(values: pd.Series) -> pd.Series:
    """Mark a value outside [0, 1], beyond ``BOUND_TOLERANCE``; missing passes."""
    return (values < -BOUND_TOLERANCE) | (values > 1 + BOUND_TOLERANCE)


SOFT_EXPECTATIONS: dict[str, Callable[[pd.Series], pd.Series]] = {
    "expect_value": _missing,
    "expect_non_negative": _negative,
    "expect_positive": _not_positive,
    "expect_probability": _outside_unit,
}
"""Each soft-expectation flag and the test that marks a breach; never raised."""

_VIOLATION_COLUMNS = ["context", "flag", "column", "value"]


def soft_violations(
    df: pd.DataFrame, schema: Schema, *, context: str, grain: Sequence[str]
) -> pd.DataFrame:
    """
    Return one row per breach of a soft expectation in ``df``.

    Parameters
    ----------
    df : pandas.DataFrame
        The table, for example a layer's output.
    schema : Schema
        Its schema; columns tagged with a ``SOFT_EXPECTATIONS`` flag are scanned.
        A tagged column absent from ``df`` is skipped.
    context : str
        The table's name, written on every row.
    grain : sequence of str
        Key columns copied onto each row so a breach traces to its row
        (``symbol``, ``date``); those absent from ``df`` are left out.

    Returns
    -------
    pandas.DataFrame
        Columns ``context``, ``flag``, ``column``, ``value``, then the grain columns;
        ordered by flag, then column in schema order, then row. No rows when nothing
        is breached.
    """
    keys = [c for c in grain if c in df.columns]
    parts: list[pd.DataFrame] = []
    for flag, breached in SOFT_EXPECTATIONS.items():
        for column, meta in schema.items():
            if not meta.get(flag) or column not in df.columns:
                continue
            mask = breached(df[column])
            if not mask.any():
                continue
            rows = df.loc[mask, keys].copy()
            rows.insert(0, "value", df.loc[mask, column])
            rows.insert(0, "column", column)
            rows.insert(0, "flag", flag)
            rows.insert(0, "context", context)
            parts.append(rows)
    if not parts:
        return pd.DataFrame(columns=_VIOLATION_COLUMNS + keys)
    return pd.concat(parts, ignore_index=True)


def expectation_notices(
    df: pd.DataFrame, schema: Schema, *, context: str, grain: Sequence[str]
) -> list[Notice]:
    """
    Return one notice per soft expectation breached in ``df``, category ``unexpected``.

    Built from ``soft_violations``, so the summary and the rows cannot disagree.
    """
    rows = soft_violations(df, schema, context=context, grain=grain)
    notices: list[Notice] = []
    for flag in SOFT_EXPECTATIONS:
        group = rows[rows["flag"] == flag]
        if group.empty:
            continue
        columns = list(dict.fromkeys(group["column"]))
        notices.append(
            Notice(
                context=f"{context}:{flag}",
                message=f"{len(group)} row(s) breach '{flag}' on {columns}",
                category="unexpected",
            )
        )
    return notices
