"""
value_investing/schema.py
-------------------------
The canonical columns of the value-investing pipeline: its inputs and, per layer, the
columns each layer produces.

The rule columns depend on the rules run (``[rules.<ID>]`` in ``config/rules.toml``)
and the points on the number of buckets, so the schema is built from them by
``pipeline_schema``.

Most constraints hold by construction of the owning layer: a flag is 0, 1 or missing, a
learned score is non-negative because the learned weights are floored at 0. Some rest on
the stored tables instead, which are checked as they are read (``INPUT_TABLES``): a
positive ``close`` (``PRICE_SCHEMA``) and a ``gics_sector`` for every member
(``CONSTITUENT_SCHEMA``) are hard here too, since a gap there is a real defect, and
``pe_average`` is positive given a positive ``close``. ``market_cap`` and ``pb`` rest on EDGAR's
first-reported share counts, which can be wrong in a single filing; they are soft
expectations, reported and never raised, so one bad filing cannot stop a run.

Owns
----
The names, dtypes, constraints and owning layer of every column of the buyability
table, and the list of stored tables the pipeline reads (their schemas are
``market_data``'s).

Must not
--------
Compute, validate or read anything (``value_investing.validation`` runs the checks);
hold thresholds (``config/rules.toml``).

Public API
----------
KEY
    The grain of the buyability table: ``symbol``, ``date``.
INPUT_TABLES
    The stored tables the pipeline reads, with their schemas.
pipeline_schema(rule_ids, *, buckets)
    The ``PipelineSchema`` for the configured rules.
buyability_schema(pipeline)
    The schema of the buyability table: every input and output, keyed on ``KEY``.

Dependency rule
---------------
``skatkis.pipelines``, ``market_data.sources`` and ``value_investing.rules``.
"""

from collections.abc import Sequence

from Toolbox.market_data.sources.constituents import CHANGE_SCHEMA, CONSTITUENT_SCHEMA
from Toolbox.market_data.sources.edgar import FACTS_TABLE_SCHEMA
from Toolbox.market_data.sources.prices import (
    DIVIDEND_SCHEMA,
    LISTING_SCHEMA,
    PRICE_SCHEMA,
    SPLIT_SCHEMA,
)
from Toolbox.skatkis.pipelines.contracts import Schema
from Toolbox.skatkis.pipelines.schema import (
    PipelineSchema,
    allowed_values,
    expect_non_negative,
    identifier,
    non_negative,
    positive,
    probability,
    required,
    type_date,
    type_float,
    type_int,
    type_str,
    unique_key,
)
from Toolbox.value_investing.rules import (
    RULES,
    pass_column,
    points_column,
    value_column,
)

KEY = ("symbol", "date")

INPUT_TABLES: dict[str, Schema] = {
    "facts": FACTS_TABLE_SCHEMA,
    "prices": PRICE_SCHEMA,
    "dividends": DIVIDEND_SCHEMA,
    "splits": SPLIT_SCHEMA,
    "listings": LISTING_SCHEMA,
    "constituents": CONSTITUENT_SCHEMA,
    "changes": CHANGE_SCHEMA,
}
"""The stored tables the pipeline reads, by table name, with the schema each is checked
against when read; the schemas are owned by the ``market_data`` source modules."""

# A rule's flag: 1 passed, 0 failed, missing when not evaluable (value_investing.flags).
_FLAG = type_float | allowed_values({0.0, 1.0})

INPUTS: Schema = {
    "symbol": type_str | identifier | required,
    "date": type_date | required,
    "gics_sector": type_str | identifier | required,
}
"""The columns that come from the stored tables rather than a layer."""

RULE_INPUTS: Schema = {
    "close": type_float | required | positive,
}

VALUATION: Schema = {
    "market_cap": type_float | expect_non_negative,
    "average_eps": type_float,
    "pe_average": type_float | positive,
    "pb": type_float | expect_non_negative,
}


def _rule_layer(rule_id: str) -> Schema:
    """Return the columns one rule produces: its value and its flag."""
    return {value_column(rule_id): dict(type_float), pass_column(rule_id): dict(_FLAG)}


def _points_layer(rule_ids: Sequence[str], buckets: int) -> Schema:
    """Return the points columns: whole grades 0 to ``buckets - 1``, missing if not evaluable."""
    grades = allowed_values({float(g) for g in range(buckets)})
    return {points_column(r): type_float | non_negative | grades for r in rule_ids}


def _score_layer(rule_ids: Sequence[str]) -> Schema:
    """Return the score columns, with one ``score_<F>`` per family of the rules run."""
    families = dict.fromkeys(RULES[r].family for r in rule_ids)
    return {
        "score": type_float | probability,
        **{f"score_{f}": type_float | probability for f in families},
        "score_binned": type_float | non_negative,
        "score_binned_weighted": type_float | non_negative,
        "score_weighted_share": type_float | probability,
        "n_passed": type_int | required | non_negative,
        "n_available": type_int | required | non_negative,
    }


def pipeline_schema(rule_ids: Sequence[str], *, buckets: int) -> PipelineSchema:
    """
    Return the pipeline schema for the rules run.

    Parameters
    ----------
    rule_ids : sequence of str
        The rules run, as in ``[rules.<ID>]`` of ``config/rules.toml``; each must be in
        ``value_investing.rules.RULES``.
    buckets : int
        The number of grade buckets (``[score] buckets``).

    Returns
    -------
    PipelineSchema
        The inputs and one layer per stage: ``rule_inputs``, ``valuation``, one
        ``rules.<ID>`` per rule, ``points``, ``score`` and ``score_ic``.

    Raises
    ------
    KeyError
        If a rule ID is not supported.
    """
    layers: dict[str, Schema] = {"rule_inputs": RULE_INPUTS, "valuation": VALUATION}
    layers |= {f"rules.{r}": _rule_layer(r) for r in rule_ids}
    layers["points"] = _points_layer(rule_ids, buckets)
    layers["score"] = _score_layer(rule_ids)
    layers["score_ic"] = {"score_ic": type_float | non_negative}
    return PipelineSchema(inputs=INPUTS, layers=layers, segmentation_source="universe")


def buyability_schema(pipeline: PipelineSchema) -> Schema:
    """Return the buyability table's schema: every input and output, keyed on ``KEY``."""
    schema = {c: pipeline.metadata(c) for c in [*pipeline.inputs, *pipeline.outputs]}
    for column in KEY:
        schema[column] = schema[column] | unique_key
    return schema
