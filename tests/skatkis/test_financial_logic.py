"""The price trend and the loan schedule (skatkis/financial_logic.py)."""

import math

import numpy as np
import pandas as pd
import pytest

from Toolbox.skatkis.financial_logic import amortise, price_trend

WINDOWS = {"trend_days": 2, "smooth_days": 3, "high_days": 2, "range_days": 3}


def _series(values: list[float]) -> pd.Series:
    dates = pd.bdate_range("2026-01-05", periods=len(values))
    return pd.Series(values, index=dates, dtype=float)


# --- price_trend ---------------------------------------------------------------------


def test_price_trend_hand_series() -> None:
    # Positive prices 10, 20, 15, 30 (the 0 on the third date is dropped).
    # smooth_days = 3 gives alpha = 2 / (3 + 1) = 0.5 for the exponential mean of ln P.
    prices = _series([10.0, 20.0, 0.0, 15.0, 30.0])
    trend = price_trend(prices, **WINDOWS)
    assert list(trend.index) == [prices.index[i] for i in (0, 1, 3, 4)]
    assert trend["price"].tolist() == [10.0, 20.0, 15.0, 30.0]
    assert math.isnan(trend["trend_mean"].iloc[0])
    assert trend["trend_mean"].iloc[1:].tolist() == pytest.approx([15.0, 17.5, 22.5])
    assert trend["high"].tolist() == [10.0, 20.0, 20.0, 30.0]
    assert trend["from_high"].tolist() == pytest.approx([0.0, 0.0, -0.25, 0.0])
    assert trend["from_trend"].iloc[1:].tolist() == pytest.approx(
        [20 / 15 - 1, 15 / 17.5 - 1, 30 / 22.5 - 1]
    )
    # Range of the last 3: (P - L) / (U - L); L = U on the first date.
    assert math.isnan(trend["in_range"].iloc[0])
    assert trend["in_range"].iloc[1:].tolist() == pytest.approx([1.0, 0.5, 1.0])
    s1 = math.log(10)
    s2 = 0.5 * s1 + 0.5 * math.log(20)
    s3 = 0.5 * s2 + 0.5 * math.log(15)
    s4 = 0.5 * s3 + 0.5 * math.log(30)
    assert math.isnan(trend["slope"].iloc[0])
    assert trend["slope"].iloc[1:].tolist() == pytest.approx(
        [252 * (s2 - s1), 252 * (s3 - s2), 252 * (s4 - s3)]
    )


def test_price_trend_missing_trend_mean_before_a_full_window() -> None:
    trend = price_trend(_series([10.0, 11.0, 12.0]), **{**WINDOWS, "trend_days": 3})
    assert trend["trend_mean"].isna().tolist() == [True, True, False]
    assert trend["from_trend"].isna().tolist() == [True, True, False]
    assert trend["trend_mean"].iloc[-1] == pytest.approx(11.0)


def test_price_trend_in_range_is_0_at_the_low_and_1_at_the_high() -> None:
    falling = price_trend(_series([30.0, 20.0, 10.0]), **WINDOWS)
    assert falling["in_range"].iloc[1:].tolist() == [0.0, 0.0]
    rising = price_trend(_series([10.0, 20.0, 30.0]), **WINDOWS)
    assert rising["in_range"].iloc[1:].tolist() == [1.0, 1.0]


def test_price_trend_in_range_is_missing_on_a_flat_range() -> None:
    trend = price_trend(_series([10.0, 10.0, 10.0]), **WINDOWS)
    assert trend["in_range"].isna().all()
    assert trend["from_high"].tolist() == [0.0, 0.0, 0.0]
    assert trend["slope"].iloc[1:].tolist() == [0.0, 0.0]


def test_price_trend_slope_is_252_times_the_daily_change_of_the_smoothed_log() -> None:
    # A steady 1% a day: with smooth_days = 1 (alpha = 1) the smoothed log is ln P.
    prices = _series([100 * 1.01**k for k in range(5)])
    trend = price_trend(prices, **{**WINDOWS, "smooth_days": 1})
    assert trend["slope"].iloc[1:].tolist() == pytest.approx([252 * math.log(1.01)] * 4)


@pytest.mark.parametrize("bad", [0.0, -5.0, np.nan])
def test_price_trend_drops_bad_prices_before_counting_windows(bad: float) -> None:
    clean = price_trend(_series([10.0, 20.0, 15.0]), **WINDOWS)
    dirty = price_trend(_series([10.0, bad, 20.0, 15.0]), **WINDOWS)
    assert len(dirty) == 3
    pd.testing.assert_frame_equal(
        dirty.reset_index(drop=True), clean.reset_index(drop=True)
    )


def test_price_trend_of_no_positive_price_is_empty() -> None:
    trend = price_trend(_series([0.0, -1.0]), **WINDOWS)
    assert trend.empty


def test_price_trend_has_no_look_ahead() -> None:
    values = [10.0, 12.0, 9.0, 14.0, 30.0, 5.0, 11.0]
    full = price_trend(_series(values), **WINDOWS)
    early = price_trend(_series(values[:4]), **WINDOWS)
    pd.testing.assert_frame_equal(full.iloc[:4], early)


def test_price_trend_does_not_mutate_its_input() -> None:
    prices = _series([10.0, 0.0, 20.0])
    before = prices.copy()
    price_trend(prices, **WINDOWS)
    pd.testing.assert_series_equal(prices, before)


# --- amortise ------------------------------------------------------------------------


def test_amortise_one_month() -> None:
    # 1% a month on 1200: interest 12, principal 112 - 12 = 100.
    schedule = amortise(1200.0, annual_rate=0.12, payment=112.0, months=1)
    assert schedule.to_dict("records") == [
        pytest.approx(
            {"month": 1.0, "interest": 12.0, "principal": 100.0, "balance": 1100.0}
        )
    ]


def test_amortise_cuts_the_final_payment_and_then_stops() -> None:
    # m1: interest 1, principal 59, balance 41; m2: interest 0.41, principal 41 (cut);
    # m3: nothing owed.
    schedule = amortise(100.0, annual_rate=0.12, payment=60.0, months=3)
    assert schedule["month"].tolist() == [1.0, 2.0, 3.0]
    assert schedule["interest"].tolist() == pytest.approx([1.0, 0.41, 0.0])
    assert schedule["principal"].tolist() == pytest.approx([59.0, 41.0, 0.0])
    assert schedule["balance"].tolist() == pytest.approx([41.0, 0.0, 0.0])


def test_amortise_balance_grows_when_the_payment_misses_the_interest() -> None:
    # m1: interest 10, principal -5 -> 1005; m2: interest 10.05, principal -5.05.
    schedule = amortise(1000.0, annual_rate=0.12, payment=5.0, months=2)
    assert schedule["principal"].tolist() == pytest.approx([-5.0, -5.05])
    assert schedule["balance"].tolist() == pytest.approx([1005.0, 1010.05])


def test_amortise_zero_balance_owes_nothing() -> None:
    schedule = amortise(0.0, annual_rate=0.12, payment=50.0, months=2)
    assert schedule[["interest", "principal", "balance"]].to_numpy().tolist() == [
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0],
    ]


def test_amortise_zero_rate_repays_in_equal_steps() -> None:
    schedule = amortise(100.0, annual_rate=0.0, payment=30.0, months=4)
    assert schedule["principal"].tolist() == pytest.approx([30.0, 30.0, 30.0, 10.0])
    assert schedule["balance"].tolist() == pytest.approx([70.0, 40.0, 10.0, 0.0])


def test_amortise_no_months_gives_no_rows() -> None:
    assert amortise(100.0, annual_rate=0.1, payment=10.0, months=0).empty
