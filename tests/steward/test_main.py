"""The personal report's command and where it writes (steward/__main__.py)."""

import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.steward.synthetic import FINANCES_TOML, REPO, make_buy_report
from Toolbox.steward import __main__ as cli

AS_OF = "2026-11-19"
TARGET = f"private/steward/reports/{AS_OF}"

TEXT_TOML = """
title = "Personal report"
abstract = "Net worth {net_worth}; buy list {buy_total} {currency}."

[portfolio]
title = "Portfolio"
text = "{listed} listed."
worth_caption = "Worth"
allocation_title = "Allocation"
allocation_text = "Over {largest_overweight}."
allocation_caption = "Allocation"

[property]
title = "{property_name}"
text = "Bond {bond}."
cash_caption = "Cash"
projection_title = "Projection"
projection_text = "{scenario_1} and {scenario_2}."
projection_caption = "Projection"
figure = "Paths"

[retirement]
title = "Retirement"
text = "At {retirement_age}."
caption = "At retirement"
"""


def _args(tmp_path: Path) -> list[str]:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "finances.toml").write_text(FINANCES_TOML)
    (inputs / "text.toml").write_text(TEXT_TOML)
    (inputs / "rules.toml").write_text("")
    return [
        "report",
        "--as-of",
        AS_OF,
        "--data-dir",
        str(tmp_path / "data"),
        "--finances",
        str(inputs / "finances.toml"),
        "--text",
        str(inputs / "text.toml"),
        "--rules",
        str(inputs / "rules.toml"),
        "--indices",
        str(inputs / "indices.toml"),
        "--value-text",
        str(REPO / "config" / "report_value_investing.toml"),
    ]


def _files(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


def _stub(
    monkeypatch: pytest.MonkeyPatch, *, engine: str | None, fails: bool = False
) -> dict[str, Any]:
    """Stub the value tool's reads and the LaTeX engine; record what was passed."""
    seen: dict[str, Any] = {}

    def inputs(**kwargs: Any) -> object:
        seen.update(kwargs)
        return make_buy_report(kwargs["folder"])

    def compile_tex(tex: Path, *, engine: str, cache: Path) -> Path:
        seen["cache"] = cache
        if fails:
            raise subprocess.CalledProcessError(1, [engine], stderr=b"! LaTeX error")
        tex.with_suffix(".log").write_text("log")
        pdf = tex.with_suffix(".pdf")
        pdf.write_bytes(b"%PDF")
        return pdf

    monkeypatch.setattr(cli, "buy_report_inputs", inputs)
    monkeypatch.setattr(cli, "compile_pdf", compile_tex)
    monkeypatch.setattr(cli.shutil, "which", lambda _name: engine)
    return seen


def test_report_keeps_only_the_pdf_under_data_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # a stray relative write would land here
    seen = _stub(monkeypatch, engine="/stub/tectonic")
    assert cli.main(_args(tmp_path)) == 0
    assert _files(tmp_path / "data") == [f"{TARGET}/personal_report.pdf"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["data", "inputs"]
    # The build ran in a temporary folder under the private target, since removed.
    folder: Path = seen["folder"]
    assert folder.parent == tmp_path / "data" / TARGET
    assert not folder.exists()


def test_report_passes_the_private_amounts_to_the_value_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _stub(monkeypatch, engine="/stub/tectonic")
    cli.main(_args(tmp_path))
    assert seen["amounts"] == {
        "currency": "ZAR",
        "picks_amount": 5000.0,
        "fixed": {"NVX": 1000.0},
    }
    assert seen["index"] == "sp500"
    assert str(seen["as_of"]) == AS_OF


def test_report_without_the_engine_keeps_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(monkeypatch, engine=None)
    assert cli.main(_args(tmp_path)) == 1
    assert _files(tmp_path / "data") == []


def test_report_failed_compile_keeps_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(monkeypatch, engine="/stub/tectonic", fails=True)
    assert cli.main(_args(tmp_path)) == 1
    assert _files(tmp_path / "data") == []


def test_the_default_inputs_are_private() -> None:
    args = cli._parser().parse_args(["report", "--as-of", AS_OF])
    assert args.finances == Path("data/private/steward/finances.toml")
    assert args.text == Path("data/private/steward/report_text.toml")
