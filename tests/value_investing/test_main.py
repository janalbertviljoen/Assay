"""The gated reads of the stored tables and the ``buyability --no-plots`` and ``buy``
commands (value_investing/__main__.py)."""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from Toolbox.market_data.sources.constituents import CONSTITUENT_COLUMNS
from Toolbox.skatkis.io.tables import write_table
from Toolbox.skatkis.pipelines.validation import SchemaValidationError
from Toolbox.value_investing import __main__ as cli
from Toolbox.value_investing.io import company_names as _company_names
from Toolbox.value_investing.io import read_input as _read
from Toolbox.value_investing.pipeline import Buyability

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


# --- the commands, with the stored tables and the LaTeX engine stubbed ---------------

INDICES = """
[aaa]
label = "AAA 100"
benchmark = "^AAATR"
benchmark_name = "AAA 100 total return"
membership = "aaa100"
"""
AS_OF = "2026-11-19"


def _configs(tmp_path: Path) -> list[str]:
    (tmp_path / "indices.toml").write_text(INDICES)
    (tmp_path / "rules.toml").write_text('[universe]\nviews = ["all", "large"]\n')
    (tmp_path / "market.toml").write_text("")
    (tmp_path / "text.toml").write_text("")
    return [
        "--as-of",
        AS_OF,
        "--index",
        "aaa",
        "--data-dir",
        str(tmp_path / "data"),
        "--results-dir",
        str(tmp_path / "results"),
        "--rules",
        str(tmp_path / "rules.toml"),
        "--indices",
        str(tmp_path / "indices.toml"),
        "--market-config",
        str(tmp_path / "market.toml"),
        "--report-text",
        str(tmp_path / "text.toml"),
    ]


def _files(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


def test_buyability_no_plots_writes_the_tables_and_weights_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    day = pd.Timestamp("2026-09-30")
    scored = pd.DataFrame({"symbol": ["AAA"], "date": [day], "score": [0.5]})
    tables = SimpleNamespace(
        prices=pd.DataFrame(), universe=pd.DataFrame({"symbol": ["AAA"]})
    )
    excess = pd.Series(
        [0.1],
        index=pd.MultiIndex.from_tuples([("AAA", day)], names=["symbol", "date"]),
        name="forward_excess",
    )
    monkeypatch.setattr(cli, "_load_tables", lambda *_: tables)
    monkeypatch.setattr(
        cli,
        "buyability",
        lambda *_, **__: Buyability(
            table=scored,
            correlations=pd.DataFrame(),
            weights=pd.DataFrame({"g2a": [1.0]}, index=[day]),
        ),
    )
    monkeypatch.setattr(cli.diagnostics, "forward_excess", lambda *_, **__: excess)
    assert cli.main(["buyability", *_configs(tmp_path), "--no-plots"]) == 0
    assert _files(tmp_path / "results") == [
        f"value_investing/aaa/{AS_OF}/buyability/rule_weights_all.csv",
        f"value_investing/aaa/{AS_OF}/buyability/rule_weights_large.csv",
    ]
    stored = tmp_path / "data" / "interim" / "value_investing" / AS_OF / "aaa"
    assert [f for f in _files(stored) if f.endswith(".parquet")] == [
        "buyability_all.parquet",
        "buyability_large.parquet",
    ]
    table = pd.read_parquet(stored / "buyability_all.parquet")
    assert table["forward_excess"].tolist() == [0.1]


def _stub_buy(
    monkeypatch: pytest.MonkeyPatch, *, compiled: bool, code: int = 0
) -> dict[str, Any]:
    """Stub the inputs, the LaTeX and the engine; record what the command passed."""
    seen: dict[str, Any] = {}

    def inputs(**kwargs: Any) -> str:
        seen.update(kwargs)
        folder: Path = kwargs["folder"]
        (folder / "next_prices.png").write_bytes(b"png")
        (folder / "trends.png").write_bytes(b"png")
        return "inputs"

    def build(_inputs: object, _text: object, *, folder: Path, subtitle: str) -> Path:
        seen["subtitle"] = subtitle
        tex = folder / "buy_report.tex"
        tex.write_text("tex")
        return tex

    def compile_tex(tex: Path, _data_dir: Path) -> int:
        if compiled:
            tex.with_suffix(".pdf").write_bytes(b"%PDF")
            tex.with_suffix(".log").write_text("log")
        return code

    monkeypatch.setattr(cli, "buy_report_inputs", inputs)
    monkeypatch.setattr(cli.report, "build_buy_report", build)
    monkeypatch.setattr(cli, "_compile", compile_tex)
    return seen


def test_buy_keeps_only_the_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _stub_buy(monkeypatch, compiled=True)
    assert cli.main(["buy", *_configs(tmp_path)]) == 0
    assert _files(tmp_path / "results") == [
        f"value_investing/aaa/{AS_OF}/buy_report.pdf"
    ]
    assert not seen["folder"].exists()  # the build folder is removed
    assert seen.get("amounts") is None  # the neutral amounts of rules.toml
    assert seen["subtitle"] == f"AAA 100, data as of {AS_OF}"


def test_buy_failed_compile_keeps_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_buy(monkeypatch, compiled=False, code=1)
    assert cli.main(["buy", *_configs(tmp_path)]) == 1
    assert _files(tmp_path / "results") == []
