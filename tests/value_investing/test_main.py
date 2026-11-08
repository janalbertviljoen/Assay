"""The gated reads of the stored tables in the command line (value_investing/__main__.py)."""

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from Toolbox.market_data.sources.constituents import CONSTITUENT_COLUMNS
from Toolbox.skatkis.io.tables import write_table
from Toolbox.skatkis.pipelines.validation import SchemaValidationError
from Toolbox.value_investing.__main__ import _company_names, _read

REPO = Path(__file__).resolve().parents[2]


def _constituents() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAA", "BBB.B"],
            "security": ["Alpha Corp", "Beta Inc"],
            "gics_sector": ["Energy", "Utilities"],
            "gics_sub_industry": ["Oil", "Electric"],
            "date_added": pd.to_datetime(["2001-01-02", None]),
            "cik": [1, None],
        }
    ).astype(CONSTITUENT_COLUMNS)


def test_read_returns_a_clean_stored_table(tmp_path: Path) -> None:
    write_table(_constituents(), tmp_path / "constituents.parquet")
    table = _read(tmp_path, "constituents")
    assert table["symbol"].tolist() == ["AAA", "BBB.B"]


def test_read_rejects_a_table_that_breaks_its_schema(tmp_path: Path) -> None:
    corrupted = _constituents()
    corrupted.loc[1, "symbol"] = "AAA"
    write_table(corrupted, tmp_path / "constituents.parquet")
    with pytest.raises(SchemaValidationError, match="Duplicate rows on key") as caught:
        _read(tmp_path, "constituents")
    assert caught.value.context == f"{tmp_path}/constituents"


def test_read_rejects_a_table_with_an_extra_column(tmp_path: Path) -> None:
    write_table(_constituents().assign(extra=1), tmp_path / "constituents.parquet")
    with pytest.raises(ValueError, match="Undeclared columns: \\['extra'\\]"):
        _read(tmp_path, "constituents")


def test_read_of_a_table_the_pipeline_does_not_read_raises(tmp_path: Path) -> None:
    write_table(_constituents(), tmp_path / "observations.parquet")
    with pytest.raises(KeyError):
        _read(tmp_path, "observations")


def test_company_names_are_keyed_by_price_symbol(tmp_path: Path) -> None:
    path = tmp_path / "constituents.parquet"
    write_table(_constituents(), path)
    assert _company_names(path) == {"AAA": "Alpha Corp", "BBB-B": "Beta Inc"}


def test_company_names_read_through_the_gate(tmp_path: Path) -> None:
    corrupted = _constituents()
    corrupted.loc[0, "gics_sector"] = None
    path = tmp_path / "constituents.parquet"
    write_table(corrupted, path)
    with pytest.raises(SchemaValidationError, match="'gics_sector'"):
        _company_names(path)


def test_the_tool_does_not_load_the_update_module() -> None:
    code = (
        "import sys, Toolbox.value_investing.__main__; "
        "sys.exit('Toolbox.market_data.update' in sys.modules)"
    )
    done = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO, capture_output=True, check=False
    )
    assert done.returncode == 0, done.stderr.decode()
