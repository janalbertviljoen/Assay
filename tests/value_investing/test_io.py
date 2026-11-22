"""The stored-table readers and the buy report's inputs (value_investing/io.py)."""

from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from Toolbox.market_data.sources.fred import OBSERVATION_COLUMNS
from Toolbox.skatkis.io.tables import write_table
from Toolbox.skatkis.pipelines.validation import SchemaValidationError
from Toolbox.value_investing import io

INDICES = """
[aaa]
label = "AAA 100"
benchmark = "^AAATR"
benchmark_name = "AAA 100 total return"
membership = "aaa100"
buy_list = true

[bbb]
label = "BBB 200"
benchmark = "^BBBTR"
benchmark_name = "BBB 200 total return"
membership = "bbb200"
"""


def _indices(tmp_path: Path) -> Path:
    path = tmp_path / "indices.toml"
    path.write_text(INDICES)
    return path


# --- stored_index --------------------------------------------------------------------


def test_stored_index_folders_for_the_as_of_date(tmp_path: Path) -> None:
    entry = io.stored_index(
        "aaa", date(2026, 11, 19), tmp_path / "data", _indices(tmp_path)
    )
    interim = tmp_path / "data" / "interim"
    assert entry.label == "AAA 100"
    assert entry.benchmark == "^AAATR"
    assert entry.interim == interim
    assert entry.tables == interim / "value_investing" / "2026-11-19" / "aaa"
    assert entry.members == interim / "constituents" / "2026-11-19" / "aaa"
    assert entry.buy_list is True


def test_stored_index_buy_list_is_off_by_default(tmp_path: Path) -> None:
    entry = io.stored_index("bbb", date(2026, 11, 19), tmp_path, _indices(tmp_path))
    assert entry.buy_list is False


def test_stored_index_unknown_key_raises(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        io.stored_index("zzz", date(2026, 11, 19), tmp_path, _indices(tmp_path))


# --- read_report_table ---------------------------------------------------------------


def _observations() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "series_id": ["DEXSFUS", "DEXSFUS"],
            "date": pd.to_datetime(["2026-11-18", "2026-11-19"]),
            "value": [18.0, np.nan],
        }
    ).astype(OBSERVATION_COLUMNS)


def test_read_report_table_returns_the_observations(tmp_path: Path) -> None:
    write_table(_observations(), tmp_path / "observations.parquet")
    table = io.read_report_table(tmp_path, "observations")
    assert table["value"].iloc[0] == 18.0
    assert len(table) == 2


def test_read_report_table_checks_the_schema(tmp_path: Path) -> None:
    broken = _observations()
    broken.loc[1, "date"] = broken.loc[0, "date"]
    write_table(broken, tmp_path / "observations.parquet")
    with pytest.raises(SchemaValidationError, match="Duplicate rows on key"):
        io.read_report_table(tmp_path, "observations")


def test_read_report_table_rejects_a_pipeline_input(tmp_path: Path) -> None:
    write_table(_observations(), tmp_path / "prices.parquet")
    with pytest.raises(KeyError):
        io.read_report_table(tmp_path, "prices")


def test_read_report_table_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        io.read_report_table(tmp_path, "observations")


# --- assemble_buy_list ---------------------------------------------------------------

END = pd.Timestamp("2026-01-08")
SETTINGS: dict[str, Any] = {
    "currency": "USD",
    "fx_series": "DEXSFUS",
    "picks_amount": 600.0,
    "fixed": {},
    "rank_ramp": [3.0, 1.0],
    "blend": [2.0, 1.0],
    "trend_days": 2,
    "smooth_days": 3,
    "high_days": 2,
    "range_days": 3,
    "lag_days": 1,
    "years": 1,
    "slope_years": 1,
    "slide": 0.2,
}


def _prices() -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-05", periods=4)
    return pd.DataFrame(
        {
            "symbol": ["AAA"] * 4 + ["BBB"] * 4,
            "date": [*dates, *dates],
            "close": [10.0, 12.0, 11.0, 10.0, 20.0, 18.0, 19.0, 20.0],
        }
    )


UPCOMING = pd.DataFrame(
    {"symbol": ["AAA", "BBB"], "score": [9.0, 6.0], "weight": [0.6, 0.4]}
)


def _rates() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "series_id": ["DEXSFUS"] * 3,
            "date": pd.to_datetime(["2026-01-06", "2026-01-07", "2026-01-09"]),
            "value": [20.0, np.nan, 99.0],
        }
    )


def test_assemble_buy_list_in_usd_needs_no_rates(tmp_path: Path) -> None:
    buy = io.assemble_buy_list(_prices(), UPCOMING, END, SETTINGS, tmp_path, None)
    assert buy.settings["rate"] == 1.0
    assert buy.settings["rate_date"] == END
    assert buy.orders["score_usd"].tolist() == pytest.approx([360.0, 240.0])
    assert buy.figure == tmp_path / "trends.png"
    assert buy.figure.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["trends.png"]


def test_assemble_buy_list_turns_another_currency_into_usd(tmp_path: Path) -> None:
    settings = {**SETTINGS, "currency": "ZAR"}
    buy = io.assemble_buy_list(_prices(), UPCOMING, END, settings, tmp_path, _rates())
    # The latest value on or before END is 20 on 2026-01-06 (missing and later skipped).
    assert buy.settings["rate"] == 20.0
    assert buy.settings["rate_date"] == pd.Timestamp("2026-01-06")
    # AAA by score: 360 ZAR / 20 = 18 USD at the close of 10 = 1.8 shares.
    assert buy.orders["score_usd"].iloc[0] == pytest.approx(18.0)
    assert buy.orders["score_shares"].iloc[0] == pytest.approx(1.8)
    assert buy.settings["currency"] == "ZAR"


def test_assemble_buy_list_another_currency_without_rates_raises(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="ZAR buy list needs the FRED rates"):
        io.assemble_buy_list(
            _prices(), UPCOMING, END, {**SETTINGS, "currency": "ZAR"}, tmp_path, None
        )


def test_assemble_buy_list_without_a_rate_by_end_raises(tmp_path: Path) -> None:
    late = _rates().iloc[2:]
    with pytest.raises(IndexError):
        io.assemble_buy_list(
            _prices(), UPCOMING, END, {**SETTINGS, "currency": "ZAR"}, tmp_path, late
        )


# --- buy_report_inputs ---------------------------------------------------------------


class _StopError(Exception):
    """Raised by a stub to end ``_buy_report_inputs`` once the reads are done."""


RULES: dict[str, Any] = {
    "universe": {"views": ["all"]},
    "report": {
        "share_column": "share_x",
        "amount_usd": 1000.0,
        "buy_list": {**SETTINGS, "picks_amount": 100.0},
    },
    "ledger": {"score_column": "score_x"},
    "wallet": {"names": 2, "horizon_months": 3, "rank_weights": [0.6, 0.4]},
}


def _stub_reads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Stub the reads; record the report tables read; stop at the picks."""
    read: list[str] = []
    prices = pd.DataFrame({"symbol": ["^AAATR"], "date": [END], "close": [1.0]})

    def report_table(folder: Path, name: str) -> pd.DataFrame:
        read.append(f"{folder.parent.name}/{folder.name}/{name}")
        return _rates()

    def stop(*_: object) -> None:
        raise _StopError

    monkeypatch.setattr(io, "read_table", lambda _path: pd.DataFrame())
    monkeypatch.setattr(io, "read_input", lambda _folder, _name: prices)
    monkeypatch.setattr(io, "read_report_table", report_table)
    monkeypatch.setattr(io.buying, "next_picks", stop)
    return read


def _call(tmp_path: Path, amounts: dict[str, Any] | None) -> None:
    io.buy_report_inputs(
        as_of=date(2026, 11, 19),
        rules=RULES,
        index="aaa",
        data_dir=tmp_path,
        indices=_indices(tmp_path),
        report_text=tmp_path / "text.toml",
        folder=tmp_path / "build",
        amounts=amounts,
    )


def test_buy_report_inputs_in_usd_reads_no_rates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    read = _stub_reads(monkeypatch)
    with pytest.raises(_StopError):
        _call(tmp_path, None)
    assert read == []


def test_buy_report_inputs_in_another_currency_reads_the_fred_rates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    read = _stub_reads(monkeypatch)
    with pytest.raises(_StopError):
        _call(tmp_path, {"currency": "ZAR"})
    assert read == ["fred/2026-11-19/observations"]


def test_buy_report_inputs_amounts_replace_the_neutral_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}

    def capture(as_of: str, rules: dict[str, Any], *_: object) -> None:
        seen["as_of"] = as_of
        seen["rules"] = rules

    monkeypatch.setattr(io, "_buy_report_inputs", capture)
    amounts = {"currency": "ZAR", "picks_amount": 5000.0, "fixed": {"NVX": 1000.0}}
    _call(tmp_path, amounts)
    settings = seen["rules"]["report"]["buy_list"]
    assert seen["as_of"] == "2026-11-19"
    assert settings["currency"] == "ZAR"
    assert settings["picks_amount"] == 5000.0
    assert settings["fixed"] == {"NVX": 1000.0}
    assert settings["trend_days"] == 2  # the rest kept
    assert seen["rules"]["report"]["share_column"] == "share_x"
    # The caller's rules are untouched.
    assert RULES["report"]["buy_list"]["currency"] == "USD"
    assert RULES["report"]["buy_list"]["picks_amount"] == 100.0


def test_buy_report_inputs_without_amounts_keep_the_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        io, "_buy_report_inputs", lambda _as_of, rules, *_: seen.update(rules=rules)
    )
    _call(tmp_path, None)
    assert seen["rules"]["report"]["buy_list"] == RULES["report"]["buy_list"]


def test_buy_report_inputs_unknown_index_raises(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        io.buy_report_inputs(
            as_of=date(2026, 11, 19),
            rules=RULES,
            index="zzz",
            data_dir=tmp_path,
            indices=_indices(tmp_path),
            report_text=tmp_path / "text.toml",
            folder=tmp_path,
        )
