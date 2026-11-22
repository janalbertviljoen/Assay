"""The schema vocabulary and ``PipelineSchema`` (skatkis/pipelines/schema.py)."""

import pytest

from Toolbox.skatkis.pipelines.schema import (
    BOUND_TOLERANCE,
    PipelineSchema,
    from_dtypes,
    positive,
    required,
    type_float,
    type_str,
    unique_key,
)


def _pipeline() -> PipelineSchema:
    """Two inputs and two layers: ``prices`` makes ``close``, ``ratios`` makes ``pe``."""
    return PipelineSchema(
        inputs={
            "symbol": type_str | required,
            "sector": type_str,
        },
        layers={
            "prices": {"close": type_float | positive},
            "ratios": {"pe": dict(type_float), "pb": dict(type_float)},
        },
        segmentation_source="universe",
    )


# ---------------------------------------------------------------------------
# from_dtypes
# ---------------------------------------------------------------------------


def test_from_dtypes_keeps_the_dtype_map_order_and_adds_the_tags() -> None:
    dtypes = {"symbol": "string", "date": "datetime64[ns]", "close": "float64"}
    schema = from_dtypes(dtypes, {"close": positive, "symbol": required | unique_key})
    assert list(schema) == ["symbol", "date", "close"]
    assert schema["symbol"] == {"dtype": "string", "required": True, "unique_key": True}
    assert schema["date"] == {"dtype": "datetime64[ns]"}
    assert schema["close"] == {"dtype": "float64", "positive": True}


def test_from_dtypes_with_no_tags_gives_dtypes_only() -> None:
    assert from_dtypes({"a": "float64"}, {}) == {"a": {"dtype": "float64"}}


def test_from_dtypes_rejects_tags_for_an_undeclared_column() -> None:
    with pytest.raises(ValueError, match="undeclared columns: \\['volume'\\]"):
        from_dtypes({"close": "float64"}, {"volume": positive})


def test_from_dtypes_does_not_share_the_tag_dicts() -> None:
    tags = {"close": positive}
    schema = from_dtypes({"close": "float64"}, tags)
    schema["close"]["extra"] = True
    assert tags["close"] == {"positive": True}
    assert positive == {"positive": True}


# ---------------------------------------------------------------------------
# PipelineSchema
# ---------------------------------------------------------------------------


def test_outputs_carry_the_producing_layer() -> None:
    outputs = _pipeline().outputs
    assert list(outputs) == ["close", "pe", "pb"]
    assert outputs["close"]["produced_by"] == "prices"
    assert outputs["close"]["positive"] is True
    assert outputs["pe"]["produced_by"] == "ratios"


def test_a_column_produced_by_two_layers_is_rejected() -> None:
    with pytest.raises(ValueError, match="produced by two layers: \\['close'\\]"):
        PipelineSchema(
            inputs={},
            layers={"a": {"close": type_float}, "b": {"close": type_float}},
            segmentation_source="universe",
        )


def test_a_column_both_input_and_output_is_rejected() -> None:
    with pytest.raises(ValueError, match="both input and output: \\['close'\\]"):
        PipelineSchema(
            inputs={"close": type_float},
            layers={"a": {"close": type_float}},
            segmentation_source="universe",
        )


def test_metadata_reads_inputs_then_outputs_and_is_a_copy() -> None:
    pipeline = _pipeline()
    assert pipeline.metadata("symbol") == {"dtype": "str", "required": True}
    assert pipeline.metadata("close")["produced_by"] == "prices"
    assert pipeline.metadata("unknown") == {}
    pipeline.metadata("symbol")["changed"] = True
    assert "changed" not in pipeline.inputs["symbol"]


def test_layer_outputs_lists_only_that_layer() -> None:
    pipeline = _pipeline()
    assert list(pipeline.layer_outputs("ratios")) == ["pe", "pb"]
    assert list(pipeline.layer_outputs("prices")) == ["close"]
    assert pipeline.layer_outputs("missing") == {}


def test_required_and_expected_split_the_inputs() -> None:
    pipeline = _pipeline()
    assert pipeline.required() == ["symbol"]
    assert pipeline.expected() == ["sector"]


def test_the_layer_definitions_are_not_tagged_in_place() -> None:
    layer = {"close": type_float | positive}
    PipelineSchema(inputs={}, layers={"p": layer}, segmentation_source="universe")
    assert "produced_by" not in layer["close"]


def test_bound_tolerance_is_1e_12() -> None:
    assert BOUND_TOLERANCE == 1e-12
