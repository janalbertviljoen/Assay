"""The report's tier, worst-list and static tables, and the short buy report
(value_investing/report.py)."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pandas as pd
import pytest

from Toolbox.skatkis.io.config import load_config
from Toolbox.value_investing.buy_list import buy_list
from Toolbox.value_investing.report import (
    BuyList,
    BuyReport,
    ReportInputs,
    _static_table,
    _tier,
    _worst_table,
    build_buy_report,
    buy_report_sections,
)

REPO = Path(__file__).resolve().parents[2]

# The cut-offs of config/rules.toml ([report] tier_cutoffs).
CUTOFFS = (0.6, 0.4, 0.2)


@pytest.mark.parametrize(
    ("share", "cutoffs", "expected"),
    [
        (-0.1, CUTOFFS, "Black"),
        (0.0, CUTOFFS, "Black"),
        (0.2, CUTOFFS, "Black"),  # exactly the last cut-off is not Red
        (0.2001, CUTOFFS, "Red"),
        (0.3, CUTOFFS, "Red"),
        (0.4, CUTOFFS, "Red"),  # exactly the second cut-off is not Amber
        (0.4001, CUTOFFS, "Amber"),
        (0.6, CUTOFFS, "Amber"),  # exactly the first cut-off is not Green
        (0.6001, CUTOFFS, "Green"),
        (1.0, CUTOFFS, "Green"),
        (0.0, (0.3, 0.075, 0.0), "Black"),  # a score of 0 is Black at a 0 cut-off
        (0.01, (0.3, 0.075, 0.0), "Red"),
        (0.075, (0.3, 0.075, 0.0), "Red"),
        (0.3, (0.3, 0.075, 0.0), "Amber"),
        (0.31, (0.3, 0.075, 0.0), "Green"),
    ],
)
def test_tier_boundaries(
    share: float, cutoffs: tuple[float, float, float], expected: str
) -> None:
    assert _tier(share, cutoffs) == expected


def _inputs(worst: pd.DataFrame) -> ReportInputs:
    # ReportInputs has many fields (BuyAndHold, Managed, ...); _worst_table reads only
    # worst, names and tier_cutoffs, so a stand-in carries those.
    stand_in = SimpleNamespace(
        worst=worst,
        names={"AAA": "Alpha Corp", "BBB": "Beta Inc"},
        tier_cutoffs=CUTOFFS,
    )
    return cast(ReportInputs, cast(Any, stand_in))


def test_worst_table_rows_follow_the_input_order_with_tiers() -> None:
    worst = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB"],
            "gics_sector": ["Energy", "Utilities"],
            "score": [1.234, 5.0],
            "score_share": [0.0, 0.5],
            "score_date": [pd.Timestamp("2026-09-18")] * 2,
        }
    )
    table = _worst_table(_inputs(worst))
    assert [r[1] for r in table.rows] == ["Energy", "Utilities"]
    assert [r[2] for r in table.rows] == ["1.2", "5.0"]
    assert [r[3] for r in table.rows] == ["0.00", "0.50"]
    assert [r[4] for r in table.rows] == ["Black", "Amber"]
    assert "Alpha" in table.rows[0][0]
    assert len(table.header) == len(table.rows[0]) == 5
    assert len(table.columns.split()) == 5


def test_worst_table_empty_gives_a_none_row() -> None:
    worst = pd.DataFrame(columns=["symbol", "gics_sector", "score", "score_share"])
    table = _worst_table(_inputs(worst))
    assert table.rows == [["none", "", "", "", ""]]


def test_static_table_casts_cells_to_strings() -> None:
    spec = {
        "header": ["Year", "Excess"],
        "rows": [[2020, 1.5], ["2021", None]],
        "columns": "l r",
    }
    table = _static_table(spec, "A caption", "tab:x")
    assert table.header == ["Year", "Excess"]
    assert table.rows == [["2020", "1.5"], ["2021", "None"]]
    assert table.columns == "l r"
    assert table.caption == "A caption"
    assert table.label == "tab:x"


# --- the short buy report ------------------------------------------------------------

BUY_SETTINGS: dict[str, Any] = {
    "currency": "USD",
    "rank_ramp": [3.0, 1.0],
    "blend": [2.0, 1.0],
    "trend_days": 200,
    "slide": 0.2,
    "years": 5,
    "slope_years": 2,
    "range_days": 1260,
    "high_days": 252,
    "lag_days": 21,
    "rate": 1.0,
    "rate_date": pd.Timestamp("2026-11-19"),
}


def _value_text() -> dict[str, Any]:
    # The tracked report text, so every placeholder it names is checked.
    return load_config(REPO / "config" / "report_value_investing.toml")


def _buy_report(
    tmp_path: Path,
    *,
    fixed: dict[str, float] | None = None,
    rate: float = 1.0,
    **settings: Any,
) -> BuyReport:
    picks = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB"],
            "gics_sector": ["Energy", "Utilities"],
            "score": [9.0, 6.0],
            "score_share": [0.9, 0.6],
            "weight": [0.6, 0.4],
            "score_date": [pd.Timestamp("2026-09-30")] * 2,
        }
    )
    fixed = fixed or {}
    orders = buy_list(
        picks,
        pd.Series({"AAA": 10.0, "BBB": 20.0, "NVX": 100.0}),
        pd.Series({"AAA": 0.5, "BBB": 0.1, "NVX": 0.3}),
        rate=rate,
        picks_amount=600.0,
        ramp=(3.0, 1.0),
        blend=(2.0, 1.0),
        fixed=fixed,
    )
    states = pd.DataFrame(
        {
            "symbol": orders["symbol"],
            "price": 10.0,
            "from_high": -0.1,
            "from_trend": -0.05,
            "in_range": 0.4,
            "slope_before": -0.2,
            "slope": -0.1,
            "state": "falling, slowing",
        }
    )
    figure = tmp_path / "figures" / "trends.png"
    prices = tmp_path / "figures" / "next_prices.png"
    buy = BuyList(orders, states, {**BUY_SETTINGS, "rate": rate, **settings}, figure)
    return BuyReport(
        buy=buy,
        next_picks=picks,
        names={"AAA": "Alpha Corp", "NVX": "Nova Inc"},
        index_label="AAA 100",
        sectors={"Energy": "energy"},
        prices_figure=prices,
        pick_years=3,
        pick_scenario=2020,
    )


def test_buy_report_facts_of_a_usd_list_without_own_choices(tmp_path: Path) -> None:
    _, facts = buy_report_sections(_buy_report(tmp_path), _value_text())
    assert facts["index"] == "AAA 100"
    assert facts["picks"] == "2"
    assert facts["pick_years"] == "3"
    assert facts["pick_scenario"] == "2020"
    assert facts["next_score_date"] == "30 September 2026"
    assert facts["next_picks"] == "Alpha Corp (AAA) and BBB"
    assert facts["currency"] == "USD"
    assert facts["buy_total"] == "600"
    assert facts["picks_amount"] == "600"
    assert facts["rate_clause"] == "The money buys"
    assert facts["ramp_ratio"] == "3"
    assert facts["blend_parts"] == "2 parts rank to 1 part dip"
    assert facts["high_period"] == "the past year"
    assert facts["lag_period"] == "a month ago"
    assert facts["range_years"] == "5"
    assert facts["slide"] == "20%"
    assert facts["trend_days"] == "200"
    assert facts["trend_years"] == "5"
    assert facts["slope_years"] == "2"


def test_buy_report_without_own_choices_adds_no_clause(tmp_path: Path) -> None:
    _, facts = buy_report_sections(_buy_report(tmp_path), _value_text())
    assert facts["own_added"] == ""
    assert facts["own_clause"] == ""


def test_buy_report_facts_of_own_choices_in_another_currency(tmp_path: Path) -> None:
    inputs = _buy_report(tmp_path, fixed={"NVX": 3000.0}, rate=18.5, currency="ZAR")
    _, facts = buy_report_sections(inputs, _value_text())
    assert facts["buy_total"] == "3,600"
    assert facts["picks_amount"] == "600"
    assert facts["own_added"] == (
        ", with Nova Inc (NVX) (3,000 ZAR) added as the investor's own choice"
    )
    assert facts["own_clause"] == (
        ", and Nova Inc (NVX) (3,000 ZAR), the investor's own choice outside the model"
    )
    assert facts["rate_clause"] == (
        "The money is turned into USD at 18.50 ZAR per USD, the rate of "
        "19 November 2026, and buys"
    )


@pytest.mark.parametrize(
    ("settings", "key", "expected"),
    [
        ({"rank_ramp": [2.5, 1.0]}, "ramp_ratio", "2.5"),
        ({"rank_ramp": [4.0, 2.0]}, "ramp_ratio", "2"),
        ({"blend": [3.0, 2.0]}, "blend_parts", "3 parts rank to 2 parts dip"),
        ({"high_days": 100}, "high_period", "the last 100 trading days"),
        ({"lag_days": 10}, "lag_period", "10 trading days ago"),
        ({"range_days": 504}, "range_years", "2"),
    ],
)
def test_buy_report_facts_follow_the_settings(
    tmp_path: Path, settings: dict[str, Any], key: str, expected: str
) -> None:
    _, facts = buy_report_sections(_buy_report(tmp_path, **settings), _value_text())
    assert facts[key] == expected


def test_buy_report_sections_and_their_labels(tmp_path: Path) -> None:
    sections, _ = buy_report_sections(
        _buy_report(tmp_path, fixed={"NVX": 300.0}), _value_text()
    )
    assert len(sections) == 2
    picks, buy = sections
    assert picks.table is not None
    assert picks.table.label == "tab:next"
    assert [f.label for f in picks.figures] == ["fig:next-prices"]
    assert buy.label == "sec:buy-list"
    assert buy.table is not None
    assert buy.table.label == "tab:buy-list"
    # The total row sums each weighting: 600 for the picks and 300 fixed.
    assert buy.table.rows[-1] == ["Total", "", "", "900", "900", "900", "900"]
    (trend,) = buy.subsections
    assert trend.table is not None
    assert trend.table.label == "tab:trends"
    assert [f.label for f in trend.figures] == ["fig:trends"]


def test_buy_report_sections_without_picks_raise(tmp_path: Path) -> None:
    inputs = _buy_report(tmp_path)
    empty = BuyReport(**{**inputs.__dict__, "next_picks": inputs.next_picks.iloc[:0]})
    with pytest.raises(IndexError):
        buy_report_sections(empty, _value_text())


def test_buy_report_sections_unknown_placeholder_raises(tmp_path: Path) -> None:
    text = _value_text()
    text["buy_report"] = {**text["buy_report"], "picks_text": "{no_such_fact}"}
    with pytest.raises(KeyError):
        buy_report_sections(_buy_report(tmp_path), text)


def test_build_buy_report_writes_only_its_latex(tmp_path: Path) -> None:
    folder = tmp_path / "build"
    tex = build_buy_report(
        _buy_report(tmp_path, fixed={"NVX": 300.0}),
        _value_text(),
        folder=folder,
        subtitle="AAA 100, data as of 2026-11-19",
    )
    assert tex == folder / "buy_report.tex"
    assert [p.name for p in folder.iterdir()] == ["buy_report.tex"]
    latex = tex.read_text()
    assert "Nova Inc (NVX)" in latex
    assert "AAA 100, data as of 2026-11-19" in latex
