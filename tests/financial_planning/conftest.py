"""The parsed synthetic finances for the financial-planning tests."""

import tomllib
from typing import Any

import pytest

from tests.financial_planning.synthetic import FINANCES_TOML


@pytest.fixture
def raw() -> dict[str, Any]:
    """The parsed synthetic ``finances.toml``."""
    return tomllib.loads(FINANCES_TOML)
