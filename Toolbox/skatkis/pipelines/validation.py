"""
skatkis/pipelines/validation.py
-------------------------------
Generic validation of a table against a schema, and the hard assertions tools compose
into their gates.

``validate_from_schema`` translates the validating flags of a schema
(``skatkis.pipelines.schema``) into a Pandera ``DataFrameSchema`` and runs it in lazy
mode, so one failure lists every violated rule with its column, row count and up to
five sample rows named by their unique-key values. The schema stays the single source
of truth; Pandera is the engine. Nulls pass value checks unless the column is required,
nothing is coerced, unknown columns are allowed and dtypes are not checked.

The ``assert_*`` functions check one rule each and raise ``ValueError`` naming the
caller's context. Tools compose them, with ``validate_from_schema``, into their own
gates in the tool's ``validation.py``; no domain rule lives here.

Owns
----
The translation of schema flags to Pandera, the schema-driven validation and its error
text, and the generic hard assertions.

Must not
--------
Hold domain rules or tool gates (the tool's ``validation.py``); fill defaults, cast,
calculate, read files or orchestrate.

Public API
----------
validate_from_schema(df, schema, context)
    Run every check the schema's flags imply; raise one ``SchemaValidationError``.
to_pandera_schema(schema, context)
    The Pandera ``DataFrameSchema`` equivalent to a schema.
SchemaValidationError
    ``ValueError`` with ``context`` and Pandera's ``failure_cases``.
assert_required_columns, assert_required_if, assert_no_nulls, assert_unique_key,
assert_probability_bounds, assert_positive, assert_non_negative, assert_allowed_values,
assert_constant_columns
    One rule each; raise ``ValueError`` naming ``context``.

Dependency rule
---------------
pandas, ``pandera.pandas``, the standard library and ``skatkis.pipelines.contracts``
(the ``Schema`` type). No tool imports.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Mapping, Sequence
from typing import Any, cast

import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaErrors

from Toolbox.skatkis.pipelines.contracts import Schema

# ---------------------------------------------------------------------------
# Schema accessors
# ---------------------------------------------------------------------------


def _with_flag(schema: Schema, flag: str) -> list[str]:
    """Return the columns whose metadata has ``flag`` set to a truthy value."""
    return [col for col, meta in schema.items() if meta.get(flag)]


def _unique_key(schema: Schema) -> list[str]:
    """Return the columns flagged ``unique_key``; together they are the row key."""
    return _with_flag(schema, "unique_key")


def _allowed_values(schema: Schema) -> dict[str, set[Any]]:
    """Return each column carrying ``allowed_values`` with its allowed set."""
    return {
        col: set(meta["allowed_values"])
        for col, meta in schema.items()
        if "allowed_values" in meta
    }


def _required_if(schema: Schema) -> dict[str, tuple[str, object]]:
    """Return each column carrying ``required_if`` with its condition column and value."""
    return {
        col: cast(tuple[str, object], meta["required_if"])
        for col, meta in schema.items()
        if "required_if" in meta
    }


# ---------------------------------------------------------------------------
# Hard assertions: one rule each, raise on violation
# ---------------------------------------------------------------------------


def assert_required_columns(
    df: pd.DataFrame, required: Sequence[str], context: str
) -> None:
    """Raise if any column in ``required`` is absent from ``df``."""
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(
            f"[{context}] Missing required columns: {missing}\n"
            f"Columns present: {df.columns.tolist()}"
        )


def assert_required_if(
    df: pd.DataFrame, conditions: Mapping[str, tuple[str, object]], context: str
) -> None:
    """Raise if a column is null on a row where its ``required_if`` condition holds."""
    for column, (condition_column, value) in conditions.items():
        subset = df.loc[df[condition_column] == value]
        if subset.empty:
            continue
        assert_no_nulls(subset, [column], context)


def assert_no_nulls(df: pd.DataFrame, columns: Sequence[str], context: str) -> None:
    """Raise if any value in ``columns`` is null."""
    null_counts = df[list(columns)].isna().sum()
    nulls = null_counts[null_counts > 0]
    if not nulls.empty:
        raise ValueError(f"[{context}] Null values found:\n{nulls.to_string()}")


def assert_unique_key(
    df: pd.DataFrame, key_columns: Sequence[str], context: str
) -> None:
    """Raise if the combination of ``key_columns`` is not unique."""
    key = list(key_columns)
    duplicates = df[df.duplicated(subset=key, keep=False)]
    if not duplicates.empty:
        raise ValueError(
            f"[{context}] Duplicate rows on key {key}:\n"
            f"{duplicates[key].drop_duplicates().head().to_string()}"
        )


def assert_probability_bounds(
    df: pd.DataFrame, columns: Sequence[str], context: str
) -> None:
    """Raise if any value in ``columns`` is outside [0, 1]; nulls pass."""
    for column in columns:
        outside = df[(df[column] < 0.0) | (df[column] > 1.0)]
        if not outside.empty:
            raise ValueError(
                f"[{context}] {column!r} has values outside [0, 1]. "
                f"Min: {df[column].min():.6f}  Max: {df[column].max():.6f}"
            )


def assert_positive(df: pd.DataFrame, columns: Sequence[str], context: str) -> None:
    """Raise if any value in ``columns`` is zero or negative; nulls pass."""
    for column in columns:
        invalid = df[df[column] <= 0]
        if not invalid.empty:
            raise ValueError(
                f"[{context}] {column!r} must be > 0. "
                f"Found {len(invalid)} non-positive values. Min: {df[column].min()}"
            )


def assert_non_negative(df: pd.DataFrame, columns: Sequence[str], context: str) -> None:
    """Raise if any value in ``columns`` is negative; nulls pass."""
    for column in columns:
        invalid = df[df[column] < 0]
        if not invalid.empty:
            raise ValueError(
                f"[{context}] {column!r} must be >= 0. "
                f"Found {len(invalid)} negative values. Min: {df[column].min()}"
            )


def assert_allowed_values(
    df: pd.DataFrame, allowed: Mapping[str, set[Any]], context: str
) -> None:
    """Raise if a column holds a non-null value outside its allowed set."""
    for column, values in allowed.items():
        not_allowed = set(df[column].dropna().unique()) - values
        if not_allowed:
            raise ValueError(
                f"[{context}] Disallowed values detected in {column!r}: {not_allowed}\n"
                f"Allowed values: {values}."
            )


def assert_constant_columns(
    df: pd.DataFrame, columns: Sequence[str], context: str
) -> None:
    """Raise if any column in ``columns`` holds more than one distinct non-null value."""
    non_constant = [
        column for column in columns if df[column].dropna().unique().size > 1
    ]
    if non_constant:
        raise ValueError(
            f"[{context}] Expected constant values for columns: {non_constant}"
        )


# ---------------------------------------------------------------------------
# Schema-driven validation on Pandera
# ---------------------------------------------------------------------------


class SchemaValidationError(ValueError):
    """
    Raised by ``validate_from_schema`` with every violation found in one pass.

    Attributes
    ----------
    context : str
        The caller's context label.
    failure_cases : pandas.DataFrame
        One row per failure, from Pandera: ``column``, ``check`` (the rule's message,
        e.g. ``"must be > 0"``), ``index`` (row label, or None for a missing column)
        and ``failure_case`` (the offending value).
    """

    def __init__(
        self, message: str, *, context: str, failure_cases: pd.DataFrame
    ) -> None:
        """Store the message, the context label and Pandera's failure cases."""
        super().__init__(message)
        self.context = context
        self.failure_cases = failure_cases


# Rule messages: the Pandera check labels and the lines of the error text, worded as
# the assert_* functions word them.
_MSG_NULL = "Null values found"
_MSG_DUPLICATE = "Duplicate rows on key"
_MSG_KEY_MISSING = "Missing unique-key columns"
_MSG_PROBABILITY = "has values outside [0, 1]"
_MSG_POSITIVE = "must be > 0"
_MSG_NON_NEGATIVE = "must be >= 0"
_MSG_DISALLOWED = "Disallowed values"
_MSG_ALLOWED_MISSING = "Missing column with allowed values"
_SAMPLE_ROWS = 5


def _builtin(name: str) -> Callable[..., pa.Check]:
    """Return Pandera's built-in check ``name``; Pandera registers these untyped."""
    return cast(Callable[..., pa.Check], getattr(pa.Check, name))


def _required_if_check(column: str, condition_column: str, value: object) -> pa.Check:
    """Return a frame check: ``column`` is non-null wherever ``condition_column == value``."""

    def check(df: pd.DataFrame) -> pd.Series:
        if condition_column not in df.columns:
            return pd.Series(False, index=df.index)
        applies = df[condition_column] == value
        if column not in df.columns:
            return ~applies
        return ~(applies & df[column].isna())

    return pa.Check(
        check,
        error=f"{_MSG_NULL} in {column!r} where {condition_column} == {value!r}",
        name=f"required_if:{column}",
    )


def _columns_present_check(columns: list[str], message: str) -> pa.Check:
    """Return a frame check that fails every row when any of ``columns`` is absent."""

    def check(df: pd.DataFrame) -> pd.Series:
        present = all(c in df.columns for c in columns)
        return pd.Series(present, index=df.index)

    return pa.Check(
        check, error=f"{message}: {columns}", name=f"present:{','.join(columns)}"
    )


def to_pandera_schema(schema: Schema, context: str = "") -> pa.DataFrameSchema:
    """
    Translate a schema into the equivalent Pandera ``DataFrameSchema``.

    Only flags that validate are translated; dtypes, defaults, ownership and
    derivation are not checked here.

    Parameters
    ----------
    schema : Schema
        Column name to metadata, as in a tool's ``schema.py``.
    context : str, optional
        Name given to the Pandera schema, used in its messages.

    Returns
    -------
    pandera.pandas.DataFrameSchema

    Notes
    -----
    The translation:

    - ``required``: ``Column(required=True, nullable=False)``; otherwise
      ``Column(required=False, nullable=True)``.
    - ``probability``: ``Check.in_range(0, 1)``; ``positive``: ``Check.gt(0)``;
      ``non_negative``: ``Check.ge(0)``; ``allowed_values``: ``Check.isin``.
    - ``unique_key``: ``DataFrameSchema(unique=keys)``, every duplicate reported.
    - ``required_if``: a frame-level check on the rows where the condition holds.

    Pandera skips nulls in value checks, so a NaN passes bound and allowed-value
    checks; only ``required`` rejects nulls. An absent unique-key column, or an absent
    column carrying ``allowed_values``, fails a frame-level check with its own
    message. Unknown columns are allowed (``strict=False``) and nothing is coerced.
    """
    columns: dict[str, pa.Column] = {}
    for name, meta in schema.items():
        checks: list[pa.Check] = []
        if meta.get("probability"):
            checks.append(_builtin("in_range")(0, 1, error=_MSG_PROBABILITY))
        if meta.get("positive"):
            checks.append(_builtin("gt")(0, error=_MSG_POSITIVE))
        if meta.get("non_negative"):
            checks.append(_builtin("ge")(0, error=_MSG_NON_NEGATIVE))
        if "allowed_values" in meta:
            checks.append(
                _builtin("isin")(list(meta["allowed_values"]), error=_MSG_DISALLOWED)
            )
        required = bool(meta.get("required"))
        columns[name] = pa.Column(
            checks=checks, required=required, nullable=not required, coerce=False
        )

    frame_checks = [
        _required_if_check(column, condition_column, value)
        for column, (condition_column, value) in _required_if(schema).items()
    ]
    key = _unique_key(schema)
    if key:
        frame_checks.append(_columns_present_check(key, _MSG_KEY_MISSING))
    for name in _allowed_values(schema):
        if not schema[name].get("required"):
            frame_checks.append(_columns_present_check([name], _MSG_ALLOWED_MISSING))

    return pa.DataFrameSchema(
        columns,
        checks=frame_checks,
        unique=key or None,
        report_duplicates="all",
        strict=False,
        name=context or None,
    )


def _sample_rows(df: pd.DataFrame, labels: list[Hashable], keys: list[str]) -> str:
    """Return up to five failing rows, named by their unique-key values where present."""
    present = [
        label
        for label in dict.fromkeys(labels)
        if label is not None and label in df.index
    ]
    shown = present[:_SAMPLE_ROWS]
    if keys and all(k in df.columns for k in keys):
        sample = df.loc[shown, keys]
        names = [
            ", ".join(f"{k}={v!r}" for k, v in zip(keys, row, strict=True))
            for row in sample.itertuples(index=False)
        ]
    else:
        names = [f"row {label!r}" for label in shown]
    more = f" (+{len(present) - len(shown)} more)" if len(present) > len(shown) else ""
    return "; ".join(names) + more


def _describe_failures(
    df: pd.DataFrame, schema: Schema, cases: pd.DataFrame, context: str
) -> str:
    """Return the error text: one line per violated rule, with its count and sample rows."""
    keys = [k for k in _unique_key(schema) if k in df.columns]
    lines: list[str] = []
    missing = cases.loc[
        cases["check"] == "column_in_dataframe", "failure_case"
    ].tolist()
    if missing:
        lines.append(
            f"[{context}] Missing required columns: {missing}\n"
            f"Columns present: {df.columns.tolist()}"
        )
    rest = cases.loc[cases["check"] != "column_in_dataframe"]
    for (column, check), group in rest.groupby(
        ["column", "check"], sort=False, dropna=False
    ):
        labels: list[Hashable] = group["index"].tolist()
        n = len(dict.fromkeys(labels))
        rows = _sample_rows(df, labels, keys)
        where = f"{column!r} " if isinstance(column, str) and column in schema else ""
        if check == _MSG_DISALLOWED:
            found = sorted(set(group["failure_case"].astype(str)))
            allowed = sorted(schema[str(column)]["allowed_values"], key=str)
            lines.append(
                f"[{context}] {check} detected in {column!r}: {found}. "
                f"Allowed values: {allowed}. Rows: {rows}"
            )
        elif check in (_MSG_POSITIVE, _MSG_NON_NEGATIVE, _MSG_PROBABILITY):
            lines.append(
                f"[{context}] {where}{check}. Found {n} invalid values. Rows: {rows}"
            )
        elif check == "not_nullable":
            lines.append(
                f"[{context}] {_MSG_NULL} in {column!r}: {n} rows. Rows: {rows}"
            )
        elif check in ("multiple_fields_uniqueness", "field_uniqueness"):
            lines.append(
                f"[{context}] {_MSG_DUPLICATE} {keys or [column]}: {n} rows. Rows: {rows}"
            )
        else:
            lines.append(f"[{context}] {check}: {n} rows. Rows: {rows}")
    # A duplicate-key line repeats once per key column; keep one.
    lines = list(dict.fromkeys(lines))
    body = "\n".join(f"  - {line}" for line in lines)
    return f"[{context}] {len(lines)} schema violation(s):\n{body}"


def validate_from_schema(df: pd.DataFrame, schema: Schema, context: str) -> None:
    """
    Run every check the schema's flags imply and report all violations at once.

    Checks: required columns present and non-null; ``required_if``; ``unique_key``
    uniqueness; ``probability``, ``positive`` and ``non_negative`` bounds;
    ``allowed_values``. Bound and allowed-value checks apply only to flagged columns
    present in ``df`` and skip nulls. Adding a flag to a schema activates the matching
    check wherever that schema is validated.

    Parameters
    ----------
    df : pandas.DataFrame
        The table to check; not modified, nothing coerced.
    schema : Schema
        Column name to metadata.
    context : str
        Label for the error text, typically the source or layer name.

    Raises
    ------
    SchemaValidationError
        A ``ValueError`` listing every violation, with ``failure_cases`` attached.
    """
    try:
        # inplace: no copy of a large table; with nothing coerced, df is not changed.
        to_pandera_schema(schema, context).validate(df, lazy=True, inplace=True)
    except SchemaErrors as exc:
        # Pandera leaves failure_cases untyped; it is a DataFrame in the pandas backend.
        failures = cast(pd.DataFrame, vars(exc)["failure_cases"])
        cases = failures.reset_index(drop=True)
        message = _describe_failures(df, schema, cases, context)
        raise SchemaValidationError(
            message, context=context, failure_cases=cases
        ) from None
