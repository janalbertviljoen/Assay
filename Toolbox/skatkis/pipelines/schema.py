"""
skatkis/pipelines/schema.py
---------------------------
The schema vocabulary, source schemas by join grain, and the binding of column
ownership and layer contracts once a pipeline's sources are loaded.

A schema is a dict keyed by canonical column name; each value is a metadata dict
composed with ``|`` from the building blocks below (``type_float | required |
non_negative``). A tool declares one ``PipelineSchema`` (every input and, per layer,
every output) and one ``SourceSchema`` per stored table; ``bind`` checks them against
each other and raises once with every problem found.

Owns
----
The schema vocabulary, the join grain, the pipeline and source schemas, the ownership
map and the binding checks (key columns, ownership, requirements, grain).

Must not
--------
Hold any tool's columns (the tool's ``schema.py``); validate data values
(``skatkis.pipelines.validation``); read files or compute.

Public API
----------
type_*, required, positive, probability, non_negative, unique_key, identifier, expect_*
    Column tags, composed with ``|``.
allowed_values(values), required_if(column, value), owned_by(layer), computable_from(*columns)
    Tags that take an argument.
Grain(name, key)
    The key columns a source is keyed on; empty means broadcast.
PipelineSchema(inputs, layers, segmentation_source)
    Every input and every layer output of a pipeline.
SourceSchema(name, grain, pipeline, segments, layer_join)
    One source; ``with_mapping`` binds it to a run's mapped columns.
Finding(check, where, message), BindingError
    One problem found while binding, and all of them raised together.
Ownership, resolve_ownership(pipeline, sources)
    The column-to-owner map of a run.
requirement_findings, grain_findings, unowned_expected, bind_contract
    The individual checks and the contract builder.
bind(pipeline, sources, contracts, frames, *, default_source, findings)
    Resolve ownership, run every check, build the layer contracts.

Dependency rule
---------------
pandas, numpy and the standard library; ``skatkis.pipelines.contracts`` for type
hints only.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, cast

import numpy as np
import pandas as pd

from Toolbox.skatkis.pipelines.contracts import ColumnMeta, LayerContract, Schema

# ---------------------------------------------------------------------------
# Vocabulary: column tags, composed with ``|`` into a schema entry
# ---------------------------------------------------------------------------

required = {"required": True}
positive = {"positive": True}
probability = {"probability": True}
unique_key = {"unique_key": True}
identifier = {"identifier": True}
"""String key whose case is kept when cast (other strings are lower-cased)."""
non_negative = {"non_negative": True}

# Soft validation flags: reported after the run, never raised.
expect_non_negative = {"expect_non_negative": True}
expect_value = {"expect_value": True}
expect_positive = {"expect_positive": True}
expect_probability = {"expect_probability": True}

# Default shorthands.
default_zero = {"default": 0.0}
default_nan = {"default": np.nan}

# Dtype shorthands.
type_str = {"dtype": "str"}
type_float = {"dtype": "float64"}
type_int = {"dtype": "Int64"}
type_date = {"dtype": "datetime64[ns]"}
type_bool = {"dtype": "bool"}


def allowed_values(values: set[Any]) -> ColumnMeta:
    """Flag a column whose non-null values must be members of ``values``."""
    return {"allowed_values": values}


def required_if(column: str, value: object) -> ColumnMeta:
    """Flag a column that is required only on rows where ``df[column] == value``."""
    return {"required_if": (column, value)}


DERIVABLE_FROM_KEY: str = "derivable_from"
BROADCAST_KEY: list[str] = ["all_rows"]


def owned_by(layer: str | None, produced_by: bool = True) -> ColumnMeta:
    """
    Ownership metadata naming the source or layer that owns a column.

    ``owned_by("term")`` gives ``{"produced_by": "term", "derivable_from": "term"}``;
    with ``produced_by=False`` only ``derivable_from`` is set; ``None`` gives ``{}``.
    """
    if layer is None:
        return {}
    if produced_by:
        return {"produced_by": layer, DERIVABLE_FROM_KEY: layer}
    return {DERIVABLE_FROM_KEY: layer}


COMPUTABLE_FROM_KEY: str = "computable_from"


def computable_from(*columns: str) -> ColumnMeta:
    """
    Flag a column that need not be mapped if one of ``columns`` is, because the
    source derives it from that sibling.
    """
    return {COMPUTABLE_FROM_KEY: columns}


RESULT_KEY: str = "result"
result = {RESULT_KEY: True}
"""Output flag: no other output of its layer is derived from it, so a source may supply it."""

SEGMENT_KEY: str = "segment"
segment = {SEGMENT_KEY: True}
"""Input flag: a categorical input that other sources may use as a segmentation key."""

INPUT, OUTPUT, SEGMENTATION = "input", "output", "segmentation"

# Tags that say where a column lives or whether it must be present. A source
# decides these from its key and the ownership map, so they are removed from the
# pipeline-wide entries before a source or contract uses them.
_PLACEMENT_TAGS = frozenset(
    {
        "required",
        "required_if",
        "unique_key",
        "produced_by",
        DERIVABLE_FROM_KEY,
        RESULT_KEY,
        SEGMENT_KEY,
    }
)


def _strip(meta: Mapping[str, Any]) -> ColumnMeta:
    """Column metadata without its placement tags."""
    return {k: v for k, v in meta.items() if k not in _PLACEMENT_TAGS}


# ---------------------------------------------------------------------------
# Grain
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Grain:
    """A named join grain: the key columns a source is keyed on (empty: broadcast)."""

    name: str
    key: tuple[str, ...] = ()

    @property
    def is_broadcast(self) -> bool:
        """Whether the source has no key and so applies to every row."""
        return not self.key


# ---------------------------------------------------------------------------
# Pipeline schema
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PipelineSchema:
    """
    Every column a pipeline's sources may supply (``inputs``) and, per layer, the
    columns each layer produces (``layers``), and the source that segment-tagged
    inputs belong to. ``outputs`` is every layer output, each tagged with the
    layer that produces it.
    """

    inputs: Mapping[str, ColumnMeta]
    layers: Mapping[str, Mapping[str, ColumnMeta]]
    segmentation_source: str
    outputs: Mapping[str, ColumnMeta] = field(init=False)

    def __post_init__(self) -> None:
        """Tag each layer output with its layer; reject a column produced twice or also an input."""
        outputs: Schema = {}
        repeated: list[str] = []
        for layer, schema in self.layers.items():
            for col, meta in schema.items():
                if col in outputs:
                    repeated.append(col)
                outputs[col] = dict(meta) | owned_by(layer)
        if repeated:
            raise ValueError(
                f"PipelineSchema: columns produced by two layers: {sorted(repeated)}"
            )
        overlap = sorted(set(self.inputs) & set(outputs))
        if overlap:
            raise ValueError(
                f"PipelineSchema: columns both input and output: {overlap}"
            )
        object.__setattr__(self, "outputs", outputs)

    def classify(self, column: str, source: str) -> str:
        """Input, output or segmentation, for ``column`` mapped in ``source``."""
        if column in self.outputs:
            return OUTPUT
        meta = self.inputs.get(column)
        if meta is None:
            return SEGMENTATION
        if meta.get(SEGMENT_KEY) and source != self.segmentation_source:
            return SEGMENTATION
        return INPUT

    def metadata(self, column: str) -> ColumnMeta:
        """Return the pipeline-wide entry for ``column``; empty if it is in neither."""
        if column in self.inputs:
            return dict(self.inputs[column])
        return dict(self.outputs.get(column, {}))

    def layer_outputs(self, layer: str) -> Schema:
        """Return the output schema of ``layer``, each column tagged with the layer."""
        return {
            c: dict(m) for c, m in self.outputs.items() if m.get("produced_by") == layer
        }

    def required(self) -> list[str]:
        """List the inputs that must be owned by some source."""
        return [c for c, m in self.inputs.items() if m.get("required")]

    def expected(self) -> list[str]:
        """List the inputs that may be supplied and otherwise take their default."""
        return [c for c, m in self.inputs.items() if not m.get("required")]


# ---------------------------------------------------------------------------
# Source schema
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceSchema:
    """
    One source: its name (the owner of every column it holds), its grain, the
    segmentation it always carries, and the layers that must join it.

    Declared once by the tool; ``with_mapping`` binds it to a run's column map,
    after which ``key``, ``value_columns`` and ``schema`` describe that run.
    """

    name: str
    grain: Grain
    pipeline: PipelineSchema
    segments: tuple[str, ...] = ()
    layer_join: tuple[str, ...] = ()
    mapped: tuple[str, ...] = ()

    def with_mapping(self, mapped: Iterable[str]) -> SourceSchema:
        """Return the schema bound to the internal column names a run's mapping supplies."""
        return dataclasses.replace(self, mapped=tuple(dict.fromkeys(mapped)))

    @property
    def key(self) -> list[str]:
        """Return the grain key, fixed segments and mapped segments; empty: broadcast."""
        extra = [
            c
            for c in self.mapped
            if self.pipeline.classify(c, self.name) == SEGMENTATION
        ]
        return list(dict.fromkeys([*self.grain.key, *self.segments, *extra]))

    @property
    def segment_cols(self) -> list[str]:
        """Key columns beyond the grain's own."""
        return [c for c in self.key if c not in self.grain.key]

    @property
    def missing_keys(self) -> list[str]:
        """Grain key and fixed segments absent from the mapping."""
        return [c for c in (*self.grain.key, *self.segments) if c not in self.mapped]

    @property
    def value_columns(self) -> list[str]:
        """
        Mapped inputs and outputs that are not key columns, plus any input this
        source derives from a mapped sibling (``computable_from``).
        """
        key = set(self.key)
        values = [c for c in self.mapped if c not in key]
        derived = [
            c
            for c, m in self.pipeline.inputs.items()
            if c not in values
            and c not in key
            and any(s in values for s in m.get(COMPUTABLE_FROM_KEY, ()))
        ]
        return values + derived

    def identity_mapping(self, columns: Iterable[str]) -> dict[str, str]:
        """
        Identity mapping over ``columns`` for data already in internal names: the
        inputs, the grain key and fixed segments, and the suppliable results.
        Other columns are left out; segmentation beyond the fixed segments needs
        an explicit mapping.
        """
        known = {*self.grain.key, *self.segments}
        results = {c for c, m in self.pipeline.outputs.items() if m.get(RESULT_KEY)}
        return {
            c: c
            for c in columns
            if c in self.pipeline.inputs or c in known or c in results
        }

    @property
    def schema(self) -> Schema:
        """
        The load schema: key columns first, then value columns owned by this
        source. The key columns together are unique (tagged ``unique_key`` here,
        never by the tool). Requirement is not checked at load; a required column
        defaults to NaN so a gap reaches the layer gate.
        """
        unique = unique_key if not self.missing_keys else {}
        schema = {c: _strip(self.pipeline.metadata(c)) | unique for c in self.key}
        for col in self.value_columns:
            meta = self.pipeline.metadata(col)
            entry = _strip(meta)
            if meta.get("required"):
                entry["default"] = float("nan")
            schema[col] = entry | owned_by(self.name, produced_by=False)
        return schema


# ---------------------------------------------------------------------------
# Findings: every check returns them; ``bind`` raises once with all of them
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """One problem found while binding: the check, where it was found, and what is wrong."""

    check: str
    where: str
    message: str


class BindingError(ValueError):
    """Every problem found while binding a pipeline's sources, raised together."""

    def __init__(self, findings: list[Finding]) -> None:
        self.findings = findings
        lines = [f"{len(findings)} problem(s) with the pipeline's sources:"]
        for check in dict.fromkeys(f.check for f in findings):
            lines.append(f"  {check}:")
            lines += [
                f"    [{f.where}] {f.message}" for f in findings if f.check == check
            ]
        super().__init__("\n".join(lines))


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------


@dataclass
class Ownership:
    """
    The run's ownership map: each column to the source or layer that supplies
    it, the bound source schemas it was built from, and the layer outputs a
    source supplies instead.
    """

    owners: dict[str, str]
    sources: dict[str, SourceSchema] = field(default_factory=dict[str, SourceSchema])
    supplied_outputs: dict[str, str] = field(default_factory=dict[str, str])

    def key_columns(self) -> set[str]:
        """Every column that is part of some source's key."""
        return {c for source in self.sources.values() for c in source.key}


def resolve_ownership(
    pipeline: PipelineSchema, sources: Iterable[SourceSchema]
) -> tuple[Ownership, list[Finding]]:
    """
    Build the ownership map from the bound source schemas.

    Every layer output starts owned by its producing layer. A column a source
    holds as a value is owned by that source. A column in a second source, or a
    layer output not tagged ``result``, is reported and left with its first
    owner, so the remaining checks still run.
    """
    owners = {c: m["produced_by"] for c, m in pipeline.outputs.items()}
    claimed: dict[str, str] = {}
    supplied: dict[str, str] = {}
    registered: dict[str, SourceSchema] = {}
    findings: list[Finding] = []

    for source in sources:
        registered[source.name] = source
        if source.missing_keys:
            findings.append(
                Finding(
                    "key columns", source.name, f"not mapped: {source.missing_keys}"
                )
            )

        for col in source.value_columns:
            if col in claimed:
                findings.append(
                    Finding(
                        "ownership",
                        source.name,
                        f"'{col}' is also mapped in {claimed[col]}",
                    )
                )
                continue
            if col in pipeline.outputs:
                if not pipeline.outputs[col].get(RESULT_KEY):
                    layer = pipeline.outputs[col]["produced_by"]
                    findings.append(
                        Finding(
                            "ownership",
                            source.name,
                            f"'{col}' is calculated by {layer} and cannot be supplied",
                        )
                    )
                    continue
                supplied[col] = source.name
            claimed[col] = source.name

    owners.update(claimed)
    return (
        Ownership(owners=owners, sources=registered, supplied_outputs=supplied),
        findings,
    )


def requirement_findings(
    pipeline: PipelineSchema,
    ownership: Ownership,
    frames: Mapping[str, pd.DataFrame],
) -> list[Finding]:
    """
    Every required input no source supplies.

    ``required_if`` is evaluated on the condition column's data in ``frames``
    (source name to loaded data). A ``computable_from`` group is satisfied when
    one of its members is owned. Both members always come from one source: the
    source that maps one also derives, and so owns, the other, so a second
    source mapping either is an ownership finding.
    """
    present = set(ownership.owners) | ownership.key_columns()
    findings: list[Finding] = []

    for col in pipeline.required():
        if col in present:
            continue
        siblings = pipeline.inputs[col].get(COMPUTABLE_FROM_KEY, ())
        if any(s in present for s in siblings):
            continue
        findings.append(Finding("required columns", col, "not supplied by any source"))

    for col, meta in pipeline.inputs.items():
        condition = meta.get("required_if")
        if condition is None or col in present:
            continue
        cond_col, value = cast(tuple[str, object], condition)
        owner = ownership.owners.get(cond_col)
        frame = frames.get(owner) if owner is not None else None
        if frame is not None and cond_col in frame and (frame[cond_col] == value).any():
            findings.append(
                Finding(
                    "required columns",
                    col,
                    f"required where {cond_col} is {value!r}, and not supplied by any source",
                )
            )
    return findings


def unowned_expected(
    pipeline: PipelineSchema, ownership: Ownership
) -> dict[str, object]:
    """Return the expected inputs no source supplies, with their defaults."""
    keys = ownership.key_columns()
    return {
        c: pipeline.inputs[c]["default"]
        for c in pipeline.expected()
        if c not in ownership.owners
        and c not in keys
        and "default" in pipeline.inputs[c]
    }


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------


def _read_sources(contract: LayerContract, ownership: Ownership) -> list[str]:
    """List the sources the layer joins: read for an input, or naming it in ``layer_join``."""
    names = [ownership.owners.get(c) for c in contract.input_schema]
    names += [n for n, s in ownership.sources.items() if contract.name in s.layer_join]
    return [n for n in dict.fromkeys(names) if n in ownership.sources]


def grain_findings(
    ownership: Ownership, contracts: Iterable[LayerContract]
) -> list[Finding]:
    """
    Every source a layer cannot join.

    A source's grain key must lie within the layer's seed columns. Each of its
    segmentation columns must be on the seed, produced by a layer, or held by a
    source whose own key lies within the seed, so it can be hydrated first.
    """
    findings: list[Finding] = []
    for contract in contracts:
        seed = set(contract.seed_columns)
        for name in _read_sources(contract, ownership):
            source = ownership.sources[name]
            outside = [c for c in source.grain.key if c not in seed]
            if outside:
                findings.append(
                    Finding(
                        "grain",
                        contract.name,
                        f"reads {name} at grain {source.grain.name}, "
                        f"but its seed {sorted(seed)} lacks {outside}",
                    )
                )
            for col in source.segment_cols:
                if col in seed:
                    continue
                owner = ownership.owners.get(col)
                holder = ownership.sources.get(owner) if owner is not None else None
                if owner is not None and holder is None:
                    continue  # produced by a layer
                if holder is not None and set(holder.key) <= seed:
                    continue
                findings.append(
                    Finding(
                        "segmentation",
                        contract.name,
                        f"'{col}' of {name} is not on the seed and no joinable source holds it",
                    )
                )
    return findings


def bind_contract(
    contract: LayerContract,
    pipeline: PipelineSchema,
    ownership: Ownership,
) -> LayerContract:
    """
    Build a layer's contract for this run.

    The input schema keeps the template's column names and order; each entry
    takes its tags from the pipeline schema and its ``derivable_from`` from the
    owner. Each output entry is tagged with the layer. ``model_joins`` is every
    source that names the layer in its ``layer_join``.
    """
    input_schema: Schema = {}
    for col in contract.input_schema:
        owner = ownership.owners.get(col)
        meta = pipeline.metadata(col)
        if owner is None:
            input_schema[col] = dict(contract.input_schema[col]) or meta
        elif owner in ownership.sources:
            entry = {
                k: v
                for k, v in meta.items()
                if k not in ("produced_by", DERIVABLE_FROM_KEY)
            }
            input_schema[col] = entry | owned_by(owner, produced_by=False)
        else:
            input_schema[col] = meta | owned_by(owner)

    output_schema = {
        c: dict(m) | owned_by(contract.name) for c, m in contract.output_schema.items()
    }
    model_joins = [
        n for n, s in ownership.sources.items() if contract.name in s.layer_join
    ]
    return dataclasses.replace(
        contract,
        input_schema=input_schema,
        output_schema=output_schema,
        model_joins=model_joins,
    )


# ---------------------------------------------------------------------------
# Binding: one call, one raise
# ---------------------------------------------------------------------------


@dataclass
class Binding:
    """
    A pipeline's sources bound for one run: the ownership map, the layer
    contracts built from it, and the defaults the broadcast source must hold
    for the expected inputs no source supplies.
    """

    ownership: Ownership
    contracts: list[LayerContract]
    defaults: dict[str, object]


def bind(  # noqa: PLR0913  the pipeline, its sources, contracts and frames, and two options
    pipeline: PipelineSchema,
    sources: Iterable[SourceSchema],
    contracts: Iterable[LayerContract],
    frames: Mapping[str, pd.DataFrame],
    *,
    default_source: str,
    findings: Iterable[Finding] = (),
) -> Binding:
    """
    Bind a run's sources: resolve ownership, check requirements and grains,
    assign the unsupplied expected inputs to ``default_source``, and build every
    layer contract.

    Parameters
    ----------
    pipeline : PipelineSchema
    sources : iterable of SourceSchema
        Each bound to its mapping (``SourceSchema.with_mapping``).
    contracts : iterable of LayerContract
        The layer contract templates; their input schemas name the columns.
    frames : mapping of str to DataFrame
        Each source's loaded data, by source name, for ``required_if``.
    default_source : str
        The broadcast source that holds the defaults.
    findings : iterable of Finding
        Problems found before binding (for example by ``merge_source_models``),
        reported with the rest.

    Raises
    ------
    BindingError
        Once, with every finding of every check.
    """
    contracts = list(contracts)
    earlier = list(findings)
    ownership, findings = resolve_ownership(pipeline, sources)
    findings = earlier + findings
    findings += requirement_findings(pipeline, ownership, frames)
    findings += grain_findings(ownership, contracts)
    if findings:
        raise BindingError(findings)

    defaults = unowned_expected(pipeline, ownership)
    for col in defaults:
        ownership.owners[col] = default_source

    bound = [bind_contract(c, pipeline, ownership) for c in contracts]
    return Binding(ownership=ownership, contracts=bound, defaults=defaults)
