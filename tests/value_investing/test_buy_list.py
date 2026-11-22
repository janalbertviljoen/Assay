"""The rank ramp, the buy list and the trend states (value_investing/buy_list.py)."""

import math

import numpy as np
import pandas as pd
import pytest

from Toolbox.skatkis.financial_logic import price_trend
from Toolbox.value_investing.buy_list import (
    MODEL,
    OWN,
    WEIGHTINGS,
    buy_list,
    price_trends,
    ramp_weights,
    trend_states,
)

# --- ramp_weights --------------------------------------------------------------------


def test_ramp_weights_3_to_1_over_10_runs_from_15_to_5_percent() -> None:
    weights = ramp_weights(10, first=3.0, last=1.0)
    assert weights[0] == pytest.approx(0.15)
    assert weights[-1] == pytest.approx(0.05)
    assert sum(weights) == pytest.approx(1.0)
    steps = np.diff(weights)
    assert steps == pytest.approx([steps[0]] * 9)


def test_ramp_weights_over_three() -> None:
    # Raw 3, 2, 1 over a total of 6.
    assert ramp_weights(3, first=3.0, last=1.0) == pytest.approx([0.5, 1 / 3, 1 / 6])


def test_ramp_weights_only_the_ratio_matters() -> None:
    assert ramp_weights(4, first=6.0, last=2.0) == pytest.approx(
        ramp_weights(4, first=3.0, last=1.0)
    )


def test_ramp_weights_equal_ends_give_equal_weights() -> None:
    assert ramp_weights(4, first=1.0, last=1.0) == pytest.approx([0.25] * 4)


def test_ramp_weights_one_company_gets_everything() -> None:
    assert ramp_weights(1, first=3.0, last=1.0) == [1.0]


# --- buy_list ------------------------------------------------------------------------


def _picks() -> pd.DataFrame:
    # Given out of score order; weights by score, summing to 1.
    return pd.DataFrame(
        {
            "symbol": ["CCC", "AAA", "BBB"],
            "score": [3.0, 9.0, 6.0],
            "weight": [0.2, 0.5, 0.3],
        }
    )


CLOSES = pd.Series({"AAA": 50.0, "BBB": 20.0, "CCC": 10.0, "NVX": 100.0})
IN_RANGE = pd.Series({"AAA": 0.8, "BBB": 0.1, "CCC": 0.5, "NVX": 0.3})


def _orders(**overrides: object) -> pd.DataFrame:
    settings: dict[str, object] = {
        "rate": 20.0,
        "picks_amount": 600.0,
        "ramp": (3.0, 1.0),
        "blend": (2.0, 1.0),
        "fixed": {"NVX": 300.0},
    }
    settings.update(overrides)
    picks = settings.pop("picks", _picks())
    in_range = settings.pop("in_range", IN_RANGE)
    return buy_list(picks, CLOSES, in_range, **settings)


def test_buy_list_rows_picks_by_score_then_the_fixed() -> None:
    orders = _orders()
    assert orders["symbol"].tolist() == ["AAA", "BBB", "CCC", "NVX"]
    assert orders["choice"].tolist() == [MODEL, MODEL, MODEL, OWN]
    assert orders["score"].iloc[:3].tolist() == [9.0, 6.0, 3.0]
    assert math.isnan(orders["score"].iloc[3])
    assert orders["close"].tolist() == [50.0, 20.0, 10.0, 100.0]
    assert orders["in_range"].tolist() == [0.8, 0.1, 0.5, 0.3]


def test_buy_list_amounts_under_the_four_weightings() -> None:
    orders = _orders().set_index("symbol")
    # Score: 600 x the model's weight.
    assert orders["score_amount"].tolist() == pytest.approx(
        [300.0, 180.0, 120.0, 300.0]
    )
    # Rank: steps 1/2, 1/3, 1/6 of 600 by score.
    assert orders["rank_amount"].tolist() == pytest.approx([300.0, 200.0, 100.0, 300.0])
    # Dip: the same steps by in_range, lowest first: BBB 0.1, CCC 0.5, AAA 0.8.
    assert orders["dip_amount"].tolist() == pytest.approx([100.0, 300.0, 200.0, 300.0])
    # Blend 2:1 of rank and dip: AAA (600 + 100) / 3, BBB (400 + 300) / 3, CCC 400 / 3.
    assert orders["blend_amount"].tolist() == pytest.approx(
        [700 / 3, 700 / 3, 400 / 3, 300.0]
    )


def test_buy_list_weights_are_of_all_the_money_and_sum_to_1() -> None:
    orders = _orders()
    for weighting in WEIGHTINGS:
        assert orders[f"{weighting}_weight"].sum() == pytest.approx(1.0)
    # 900 in all: AAA's 300 by score is a third, NVX's fixed 300 a third everywhere.
    assert orders["score_weight"].iloc[0] == pytest.approx(1 / 3)
    assert orders[[f"{w}_weight" for w in WEIGHTINGS]].iloc[
        3
    ].tolist() == pytest.approx([1 / 3] * 4)


def test_buy_list_usd_is_amount_over_rate_and_shares_fractional() -> None:
    orders = _orders().set_index("symbol")
    # AAA by score: 300 / 20 = 15 USD, 15 / 50 = 0.3 shares.
    assert orders.loc["AAA", "score_usd"] == pytest.approx(15.0)
    assert orders.loc["AAA", "score_shares"] == pytest.approx(0.3)
    # NVX fixed: 300 / 20 = 15 USD at 100 = 0.15 shares, the same in every weighting.
    for weighting in WEIGHTINGS:
        assert orders.loc["NVX", f"{weighting}_usd"] == pytest.approx(15.0)
        assert orders.loc["NVX", f"{weighting}_shares"] == pytest.approx(0.15)


def test_buy_list_in_usd_keeps_the_amounts() -> None:
    orders = _orders(rate=1.0)
    for weighting in WEIGHTINGS:
        assert (
            orders[f"{weighting}_usd"].tolist()
            == orders[f"{weighting}_amount"].tolist()
        )


def test_buy_list_dip_tie_goes_by_score() -> None:
    tied = pd.Series({"AAA": 0.2, "BBB": 0.2, "CCC": 0.1})
    orders = _orders(in_range=tied, fixed={}).set_index("symbol")
    # CCC lowest gets 300; AAA and BBB tie at 0.2 and go by score: AAA 200, BBB 100.
    assert orders["dip_amount"].tolist() == pytest.approx([200.0, 100.0, 300.0])


def test_buy_list_company_without_a_range_comes_last_in_the_dip() -> None:
    partial = pd.Series({"BBB": 0.1, "CCC": 0.5})
    orders = _orders(in_range=partial, fixed={}).set_index("symbol")
    assert orders["dip_amount"].tolist() == pytest.approx([100.0, 300.0, 200.0])
    assert math.isnan(orders.loc["AAA", "in_range"])


def test_buy_list_score_tie_goes_by_symbol() -> None:
    picks = pd.DataFrame(
        {"symbol": ["BBB", "AAA"], "score": [5.0, 5.0], "weight": [0.5, 0.5]}
    )
    orders = _orders(picks=picks, fixed={})
    assert orders["symbol"].tolist() == ["AAA", "BBB"]
    assert orders["rank_amount"].tolist() == pytest.approx([450.0, 150.0])


def test_buy_list_one_pick_gets_all_the_picks_money() -> None:
    picks = pd.DataFrame({"symbol": ["AAA"], "score": [9.0], "weight": [1.0]})
    orders = _orders(picks=picks, fixed={})
    for weighting in WEIGHTINGS:
        assert orders[f"{weighting}_amount"].tolist() == [600.0]
        assert orders[f"{weighting}_weight"].tolist() == [1.0]


def test_buy_list_no_picks_money_leaves_only_the_fixed() -> None:
    orders = _orders(picks_amount=0.0).set_index("symbol")
    for weighting in WEIGHTINGS:
        assert orders[f"{weighting}_amount"].iloc[:3].tolist() == [0.0, 0.0, 0.0]
        assert orders.loc["NVX", f"{weighting}_weight"] == 1.0


def test_buy_list_does_not_mutate_its_inputs() -> None:
    picks = _picks()
    before = picks.copy()
    buy_list(
        picks,
        CLOSES,
        IN_RANGE,
        rate=20.0,
        picks_amount=600.0,
        ramp=(3.0, 1.0),
        blend=(2.0, 1.0),
        fixed={"NVX": 300.0},
    )
    pd.testing.assert_frame_equal(picks, before)


# --- price_trends --------------------------------------------------------------------

WINDOWS = {"trend_days": 2, "smooth_days": 3, "high_days": 2, "range_days": 3}


def _prices() -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-05", periods=4)
    return pd.DataFrame(
        {
            "symbol": ["AAA"] * 4 + ["BBB"] * 4,
            "date": [*dates, *dates],
            "close": [10.0, 12.0, np.nan, 11.0, 50.0, 40.0, 45.0, 60.0],
        }
    ).sample(frac=1.0, random_state=0)


def test_price_trends_keeps_each_company_apart() -> None:
    prices = _prices()
    trends = price_trends(prices, ["BBB", "AAA"], **WINDOWS)
    assert list(trends.columns[:2]) == ["date", "price"]
    assert set(trends.columns) >= {"symbol", "date", "slope", "in_range"}
    for symbol in ("AAA", "BBB"):
        own = prices[prices["symbol"] == symbol].sort_values("date")
        expected = price_trend(
            own.set_index("date")["close"].dropna(), **WINDOWS
        ).reset_index()
        got = trends[trends["symbol"] == symbol].drop(columns="symbol")
        pd.testing.assert_frame_equal(
            got.reset_index(drop=True), expected, check_names=False
        )
    assert trends["symbol"].iloc[0] == "BBB"
    assert len(trends[trends["symbol"] == "AAA"]) == 3


# --- trend_states --------------------------------------------------------------------


def _trends(rows: dict[str, list[tuple[float, float]]]) -> pd.DataFrame:
    """Two dated rows per symbol of (slope, from_trend); the other measures fixed."""
    frames = []
    for symbol, values in rows.items():
        dates = pd.bdate_range("2026-01-05", periods=len(values))
        frames.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "price": 10.0,
                    "from_high": -0.1,
                    "from_trend": [v[1] for v in values],
                    "in_range": 0.4,
                    "slope": [v[0] for v in values],
                    "symbol": symbol,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


@pytest.mark.parametrize(
    ("values", "state"),
    [
        ([(-0.1, 0.0), (-0.2, -0.1)], "falling"),
        ([(-0.3, 0.0), (-0.1, -0.1)], "falling, slowing"),
        ([(-0.1, 0.0), (-0.1, -0.1)], "falling, slowing"),  # equal is not lower
        ([(-0.1, 0.0), (0.0, -0.05)], "turning up below trend"),  # slope exactly 0
        ([(-0.1, 0.0), (0.1, -0.05)], "turning up below trend"),
        ([(-0.1, 0.0), (0.1, 0.0)], "rising above trend"),  # exactly on the trend
        ([(-0.1, 0.0), (0.1, 0.2)], "rising above trend"),
        ([(np.nan, 0.0), (-0.1, 0.0)], "falling, slowing"),  # no earlier slope
        ([(-0.1, 0.0), (0.1, np.nan)], "rising above trend"),  # no trend mean
    ],
)
def test_trend_states_read_the_latest_slope(
    values: list[tuple[float, float]], state: str
) -> None:
    states = trend_states(_trends({"AAA": values}), lag_days=1)
    assert states["state"].tolist() == [state]


def test_trend_states_take_the_last_row_and_the_slope_lag_days_before() -> None:
    trends = _trends(
        {"BBB": [(0.3, 0.1), (0.2, 0.1), (0.5, 0.1)], "AAA": [(1.0, 0.0)] * 3}
    )
    states = trend_states(trends.iloc[::-1], lag_days=2)
    assert states["symbol"].tolist() == ["AAA", "BBB"]  # first seen in the input
    bbb = states.set_index("symbol").loc["BBB"]
    assert bbb["slope"] == 0.5
    assert bbb["slope_before"] == 0.3
    assert bbb["date"] == pd.Timestamp("2026-01-07")
    assert list(states.columns) == [
        "symbol",
        "date",
        "price",
        "from_high",
        "from_trend",
        "in_range",
        "slope",
        "slope_before",
        "state",
    ]


def test_trend_states_too_few_rows_raise() -> None:
    with pytest.raises(IndexError):
        trend_states(_trends({"AAA": [(0.1, 0.0)]}), lag_days=1)


def test_trend_states_of_no_trends_is_empty() -> None:
    states = trend_states(_trends({"AAA": [(0.1, 0.0)]}).iloc[:0], lag_days=1)
    assert states.empty
    assert list(states.columns) == []
