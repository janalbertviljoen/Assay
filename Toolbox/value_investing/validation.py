"""
value_investing/validation.py
-----------------------------
The value-investing gates: the checks a table must pass before it leaves a stage.

A gate composes the generic checks of ``skatkis.pipelines.validation`` with the rules
of this tool. The buyability gate checks the table against its schema
(``value_investing.schema``) and that its columns are exactly the declared ones, so only
declared output columns survive and none is silently dropped.

Owns
----
The buyability output gate.

Must not
--------
Compute, fill or reshape data (``value_investing.pipeline`` and the layers); declare
columns (``value_investing.schema``).

Public API
----------
check_buyability(table, schema)
    Raise unless the buyability table matches its schema exactly.

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

CONTEXT = "buyability"


def check_buyability(table: pd.DataFrame, schema: Schema) -> None:
    """
    Raise unless ``table`` matches the buyability schema exactly.

    Parameters
    ----------
    table : pandas.DataFrame
        The buyability table (``value_investing.pipeline.buyability``).
    schema : Schema
        Its schema (``value_investing.schema.buyability_schema``).

    Raises
    ------
    ValueError
        If the table has a column the schema does not declare, or lacks one it does;
        raised by ``assert_exact_columns`` before any constraint is checked.
    skatkis.pipelines.validation.SchemaValidationError
        If a constraint is broken; every breach is listed with sample keys. It is a
        ``ValueError`` too, so catching ``ValueError`` covers both.
    """
    assert_exact_columns(table, list(schema), CONTEXT)
    validate_from_schema(table, schema, CONTEXT)
