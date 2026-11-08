"""
skatkis/pipelines/contracts.py
------------------------------
Generic contract abstractions for declarative pipeline layer definitions.

A ``LayerContract`` is the interface of one pipeline layer. Tools declare one contract
per layer in their ``contracts.py``; ``schema.bind`` builds the contracts of a run from
the ownership of its columns, and the validation gates read them to check inputs,
outputs, grain and immutability. The contract holds metadata only and never performs
work itself.

Owns
----
- The shape of a layer contract: the fields every tool contract must use.
- Conflict-detecting schema composition (``safe_merge``).

Must not
--------
- Hold concrete contracts for any tool (each tool's ``contracts.py``).
- Validate or compute (``validation``, layer modules).

Public API
----------
LayerContract(name, seed_columns, input_schema, output_schema, grain, ...)
    Declares one layer's grain, seed columns, input and output schemas, model
    joins, immutable inputs and an optional navigation description.
safe_merge(*schemas)
    Merge schema dicts left to right, raising on conflicting definitions of the
    same column.

Dependency rule
---------------
No runtime dependency on registry implementations or domain schemas.
Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ColumnMeta = dict[str, Any]
"""One column's metadata: its dtype, constraint flags and ownership tags."""

Schema = dict[str, ColumnMeta]
"""A schema: column name to its metadata."""


@dataclass
class LayerContract:
    """
    Full interface declaration for one pipeline layer.

    Grain and model_joins are intentionally orthogonal:
    - ``grain`` defines row-level uniqueness identity for the layer output.
    - ``model_joins`` names the lookup models whose segment cols are appended
      to the base join key at hydration time.  The resolver reads
      ``model.col_map.segment_cols`` from the registry at runtime, so
      client-specific segmentation columns require no contract changes.

    Parameters
    ----------
    name : str
        Unique layer identifier — matches the registry key.
    seed_columns : list[str]
        Columns that seed the layer (e.g. ``["symbol", "date"]``).  Sliced from
        the input source before the compute function is called.
    input_schema : dict
        Columns required as layer input.
    output_schema : dict
        Columns produced by the layer.
    grain : list[str]
        Columns that together uniquely identify each output row.
    model_joins : list[str]
        Names of registered models whose segment cols are spliced into the
        join key during hydration.  Empty for layers with no model lookups.
    immutable_inputs : list[str]
        Upstream columns this layer must not overwrite.
    output_cols : list[str]
        Derived from ``output_schema.keys()`` automatically.
    description : str | None
        One or two sentences documenting what this layer produces, for
        the output workbook's navigation table
        (skatkis.pipelines.preface.build_navigation_from_registry).
        None if undocumented - the layer still runs, it just won't
        appear in navigation.
    """

    name: str
    seed_columns: list[str]
    input_schema: Schema
    output_schema: Schema
    grain: list[str]
    immutable_inputs: list[str] = field(default_factory=list[str])
    model_joins: list[str] = field(default_factory=list[str])
    output_cols: list[str] = field(default_factory=list[str])
    description: str | None = None

    def __post_init__(self) -> None:
        """Default ``output_cols`` to the output schema's column order."""
        if not self.output_cols:
            self.output_cols = list(self.output_schema.keys())

    @property
    def input_cols(self) -> list[str]:
        """Input column names, in input-schema order."""
        return list(self.input_schema.keys())

    @property
    def all_cols(self) -> list[str]:
        """Input then output column names, without duplicates, order preserved."""
        seen: dict[str, None] = {}
        for col in self.input_cols + self.output_cols:
            seen[col] = None
        return list(seen)


def safe_merge(*schemas: Schema) -> Schema:
    """
    Merge two or more schema dicts, raising on conflicting definitions.

    Exact-equality duplicates are silently accepted (same column, same
    definition reused across schemas).  Differing definitions for the same
    column name raise immediately with a clear error message.

    Parameters
    ----------
    *schemas : dict
        Two or more column schema dicts, evaluated left-to-right.

    Returns
    -------
    dict
        Merged schema dict with all unique columns from all input schemas.

    Raises
    ------
    ValueError
        If the same column appears with differing definitions. The error message
        includes both the existing and incoming definitions for debugging.
    """
    result: Schema = {}
    for schema in schemas:
        for col, definition in schema.items():
            if col in result:
                if result[col] != definition:
                    raise ValueError(
                        f"safe_merge: conflicting definitions for column '{col}'.\n"
                        f"  Existing : {result[col]}\n"
                        f"  Incoming : {definition}"
                    )
            else:
                result[col] = definition
    return result
