"""
market_data/validation.py
-------------------------
The market-data gate: the check a stored table passes where it is written and where it
is read.

A table passes when its columns are exactly those of its schema and every constraint
holds (``skatkis.pipelines.validation``); dtypes are not checked. The schemas are owned
by the source modules (``PRICE_SCHEMA``, ``FACTS_TABLE_SCHEMA``, ...), listed for the
writes in ``market_data.update.TABLE_SCHEMAS`` and, for each tool, for its reads in the
tool's ``schema.py`` (``value_investing.schema.INPUT_TABLES``).

Owns
----
The stored-table gate.

Must not
--------
Declare columns (the source modules); parse, clean or reshape data; read or write files.

Public API
----------
check_table(table, schema, context)
    Raise unless ``table`` has exactly the columns of ``schema`` and meets its
    constraints; dtypes are not checked.

Dependency rule
---------------
pandas and ``skatkis.pipelines``.
"""

import pandas as pd

from Toolbox.skatkis.pipelines.contracts import Schema
from Toolbox.skatkis.pipelines.validation import (
    assert_exact_columns,
    validate_from_schema,
)


def check_table(table: pd.DataFrame, schema: Schema, context: str) -> None:
    """
    Raise unless ``table`` has exactly the columns of ``schema`` and meets its constraints.

    Parameters
    ----------
    table : pandas.DataFrame
        A stored table, as written or read.
    schema : Schema
        Its schema.
    context : str
        The table's name for the error text, ``<source>/<table>`` (``yahoo/prices``).

    Raises
    ------
    ValueError
        If a column is undeclared or missing; raised by ``assert_exact_columns`` before
        any constraint is checked.
    skatkis.pipelines.validation.SchemaValidationError
        If a constraint is broken; every breach is listed with sample keys. It is a
        ``ValueError`` too, so catching ``ValueError`` covers both.
    """
    assert_exact_columns(table, list(schema), context)
    validate_from_schema(table, schema, context)
