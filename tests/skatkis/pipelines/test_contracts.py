"""Schema composition with ``safe_merge`` (skatkis/pipelines/contracts.py)."""

import pytest

from Toolbox.skatkis.pipelines.contracts import safe_merge


def test_disjoint_schemas_merge_in_order() -> None:
    merged = safe_merge({"a": {"dtype": "str"}}, {"b": {"dtype": "float64"}})
    assert merged == {"a": {"dtype": "str"}, "b": {"dtype": "float64"}}
    assert list(merged) == ["a", "b"]


def test_an_identical_definition_is_accepted_once() -> None:
    entry = {"dtype": "float64", "positive": True}
    merged = safe_merge({"close": dict(entry)}, {"close": dict(entry)}, {"x": {}})
    assert merged == {"close": entry, "x": {}}


def test_a_conflicting_definition_raises_with_both() -> None:
    with pytest.raises(ValueError, match="conflicting definitions for column 'close'"):
        safe_merge(
            {"close": {"dtype": "float64"}},
            {"close": {"dtype": "float64", "positive": True}},
        )


def test_a_conflict_in_a_third_schema_is_found() -> None:
    with pytest.raises(ValueError, match="'b'"):
        safe_merge({"a": {}}, {"b": {"dtype": "str"}}, {"b": {"dtype": "int"}})


def test_no_schemas_give_an_empty_schema() -> None:
    assert safe_merge() == {}


def test_the_inputs_are_not_modified() -> None:
    left = {"a": {"dtype": "str"}}
    right = {"b": {"dtype": "str"}}
    safe_merge(left, right)
    assert left == {"a": {"dtype": "str"}}
    assert right == {"b": {"dtype": "str"}}
