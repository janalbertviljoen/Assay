"""The value-investing pipeline schema and its read-side tables (value_investing/schema.py)."""

import pytest

from Toolbox.market_data.update import TABLE_SCHEMAS
from Toolbox.value_investing.schema import (
    INPUT_TABLES,
    KEY,
    buyability_schema,
    pipeline_schema,
)


def test_the_layers_follow_the_stages_and_the_rules_run() -> None:
    pipeline = pipeline_schema(["G2a", "E1"], buckets=6)
    assert list(pipeline.layers) == [
        "rule_inputs",
        "valuation",
        "rules.G2a",
        "rules.E1",
        "points",
        "score",
        "score_ic",
    ]
    assert list(pipeline.inputs) == ["symbol", "date", "gics_sector"]


def test_each_rule_gives_its_value_flag_and_points() -> None:
    pipeline = pipeline_schema(["G2a", "E1"], buckets=6)
    assert list(pipeline.layer_outputs("rules.G2a")) == ["g2a_value", "g2a_pass"]
    assert list(pipeline.layer_outputs("rules.E1")) == ["e1_value", "e1_pass"]
    assert list(pipeline.layer_outputs("points")) == ["g2a_points", "e1_points"]
    assert pipeline.outputs["g2a_pass"]["allowed_values"] == {0.0, 1.0}


def test_one_family_score_per_family_of_the_rules_run() -> None:
    score = pipeline_schema(["G2a", "G5", "E1"], buckets=6).layer_outputs("score")
    assert [c for c in score if c.startswith("score_") and len(c) == 7] == [
        "score_G",
        "score_E",
    ]
    only_g = pipeline_schema(["G2a"], buckets=6).layer_outputs("score")
    assert "score_E" not in only_g


@pytest.mark.parametrize("buckets", [1, 3, 6])
def test_the_grades_run_from_0_to_buckets_minus_1(buckets: int) -> None:
    points = pipeline_schema(["G2a"], buckets=buckets).outputs["g2a_points"]
    assert points["allowed_values"] == {float(g) for g in range(buckets)}
    assert points["non_negative"] is True


def test_an_unknown_rule_raises_key_error() -> None:
    with pytest.raises(KeyError):
        pipeline_schema(["G2a", "ZZ9"], buckets=6)


def test_no_rules_still_give_the_shared_stages() -> None:
    pipeline = pipeline_schema([], buckets=6)
    assert pipeline.layer_outputs("points") == {}
    assert "score_ic" in pipeline.outputs


def test_the_buyability_schema_keys_on_symbol_and_date() -> None:
    schema = buyability_schema(pipeline_schema(["G2a"], buckets=6))
    assert KEY == ("symbol", "date")
    assert [c for c, m in schema.items() if m.get("unique_key")] == list(KEY)


def test_the_buyability_schema_holds_every_input_and_output() -> None:
    pipeline = pipeline_schema(["G2a", "E1"], buckets=6)
    schema = buyability_schema(pipeline)
    assert list(schema) == [*pipeline.inputs, *pipeline.outputs]


def test_the_buyability_schema_does_not_tag_the_pipeline() -> None:
    pipeline = pipeline_schema(["G2a"], buckets=6)
    buyability_schema(pipeline)
    assert "unique_key" not in pipeline.inputs["symbol"]


@pytest.mark.parametrize(
    ("column", "flag"),
    [
        ("close", "positive"),
        ("pe_average", "positive"),
        ("gics_sector", "required"),
        ("score", "probability"),
        ("score_weighted_share", "probability"),
        ("score_ic", "non_negative"),
        ("n_passed", "required"),
        ("market_cap", "expect_non_negative"),
        ("pb", "expect_non_negative"),
    ],
)
def test_the_constraint_on_each_column(column: str, flag: str) -> None:
    schema = buyability_schema(pipeline_schema(["G2a"], buckets=6))
    assert schema[column].get(flag) is True


@pytest.mark.parametrize("column", ["market_cap", "pb"])
def test_share_count_ratios_are_soft_only(column: str) -> None:
    meta = buyability_schema(pipeline_schema(["G2a"], buckets=6))[column]
    assert not meta.get("non_negative") and not meta.get("positive")


@pytest.mark.parametrize("name", list(INPUT_TABLES))
def test_each_input_table_is_checked_as_the_update_writes_it(name: str) -> None:
    assert INPUT_TABLES[name] == TABLE_SCHEMAS[name]


def test_the_input_tables_are_those_the_pipeline_reads() -> None:
    assert set(INPUT_TABLES) == {
        "facts",
        "prices",
        "dividends",
        "splits",
        "listings",
        "constituents",
        "changes",
    }
