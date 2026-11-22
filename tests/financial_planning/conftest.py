"""The parsed synthetic finances for the steward's tests."""

import tomllib
from typing import Any

import pytest

from tests.steward.synthetic import FINANCES_TOML


@pytest.fixture
def raw() -> dict[str, Any]:
    """The parsed synthetic ``finances.toml``."""
    return tomllib.loads(FINANCES_TOML)
