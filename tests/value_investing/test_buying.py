"""The steps from the scored table to the buy list (value_investing/buying.py)."""

import numpy as np
import pandas as pd
import pytest

from Toolbox.value_investing import buying
from Toolbox.value_investing.buy_list import OWN

# --- report_wallet -------------------------------------------------------------------

RULES = {
    "ledger": {"score_column": "score_x"},
    "wallet": {"names": 2, "horizon_months": 3, "rank_weights": [0.6, 0.4]},
    "report": {"amount_usd": 1000.0},
}


def test_report_wallet_is_always_weighted_by_score() -> None:
    wallet = buying.report_wallet(RULES)
    assert wallet.weighting == "score"
    assert wallet.score_column == "score_x"
    assert wallet.names == 2
    assert wallet.book_usd == 1000.0
    assert wallet.horizon_months == 3
    assert wallet.rank_weights == (0.6, 0.4)


def test_report_wallet_missing_setting_raises() -> None:
    with pytest.raises(KeyError):
        buying.report_wallet({**RULES, "report": {}})


# --- next_picks ----------------------------------------------------------------------

D1 = pd.Timestamp("2026-03-31")
D2 = pd.Timestamp("2026-06-30")


def _table() -> pd.DataFrame:
    symbols = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    early = [8.0, 6.0, 4.0, 2.0, 1.0]
    late = [1.0, 2.0, 4.0, 6.0, 8.0]  # scored after the decision date: never seen
    return pd.DataFrame(
        {
            "symbol": symbols * 2,
            "date": [D1] * 5 + [D2] * 5,
            "gics_sector": ["Energy"] * 10,
            "score_x": early + late,
            "share_x": [s / 10 for s in early + late],
        }
    )


def test_next_picks_take_the_latest_scores_on_or_before_end() -> None:
    wallet = buying.report_wallet(RULES)
    picks, worst = buying.next_picks(
        _table(), D2 - pd.Timedelta(days=1), wallet, "share_x"
    )
    assert picks["symbol"].tolist() == ["AAA", "BBB"]
    assert (picks["score_date"] == D1).all()
    # Weighted by score: 8 / 14 and 6 / 14 of the 1000 USD book.
    assert picks["weight"].tolist() == pytest.approx([8 / 14, 6 / 14])
    assert picks["amount"].tolist() == pytest.approx([8000 / 14, 6000 / 14])
    assert picks["score_share"].tolist() == pytest.approx([0.8, 0.6])
    assert worst["symbol"].tolist() == ["EEE", "DDD"]
    assert {"date", "gics_sector", "score_share", "side"} <= set(picks.columns)
    assert set(picks["side"]) == {"buy"}
    assert set(worst["side"]) == {"sell"}


def test_next_picks_on_the_score_date_use_it() -> None:
    wallet = buying.report_wallet(RULES)
    picks, _ = buying.next_picks(_table(), D2, wallet, "share_x")
    assert picks["symbol"].tolist() == ["EEE", "DDD"]


def test_next_picks_lowest_scores_tie_by_symbol() -> None:
    table = _table()
    table.loc[(table["date"] == D1) & (table["symbol"] == "DDD"), "score_x"] = 1.0
    wallet = buying.report_wallet(RULES)
    _, worst = buying.next_picks(table, D1, wallet, "share_x")
    assert worst["symbol"].tolist() == ["DDD", "EEE"]


def test_next_picks_before_any_score_raise() -> None:
    wallet = buying.report_wallet(RULES)
    with pytest.raises(ValueError, match="concatenate"):
        buying.next_picks(_table(), D1 - pd.Timedelta(days=1), wallet, "share_x")


# --- latest_rate ---------------------------------------------------------------------


def _rates() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "series_id": ["DEXSFUS"] * 4 + ["OTHER"],
            "date": pd.to_datetime(
                ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-06", "2026-11-04"]
            ),
            "value": [18.0, 19.0, np.nan, 25.0, 99.0],
        }
    )


def test_latest_rate_skips_missing_values_and_later_dates() -> None:
    rates = _rates()
    before = rates.copy()
    value, day = buying.latest_rate(rates, "DEXSFUS", pd.Timestamp("2026-11-05"))
    assert value == 19.0
    assert day == pd.Timestamp("2026-11-03")
    pd.testing.assert_frame_equal(rates, before)


def test_latest_rate_on_the_end_date_is_used() -> None:
    value, day = buying.latest_rate(_rates(), "DEXSFUS", pd.Timestamp("2026-11-06"))
    assert (value, day) == (25.0, pd.Timestamp("2026-11-06"))


def test_latest_rate_without_a_value_raises() -> None:
    with pytest.raises(IndexError):
        buying.latest_rate(_rates(), "DEXSFUS", pd.Timestamp("2026-11-01"))
    with pytest.raises(IndexError):
        buying.latest_rate(_rates(), "MISSING", pd.Timestamp("2026-11-30"))


# --- prepare_buy_list ----------------------------------------------------------------

SETTINGS = {
    "picks_amount": 600.0,
    "fixed": {"NVX": 300.0},
    "rank_ramp": [3.0, 1.0],
    "blend": [2.0, 1.0],
    "trend_days": 2,
    "smooth_days": 3,
    "high_days": 2,
    "range_days": 3,
    "lag_days": 1,
}
END = pd.Timestamp("2026-01-08")


def _prices(*, after: float) -> pd.DataFrame:
    """Four closes up to ``END`` per company, then one later close of ``after``."""
    dates = pd.bdate_range("2026-01-05", periods=5)  # the fifth is after END
    closes = {
        "AAA": [10.0, 12.0, 11.0, 13.0, after],
        "BBB": [20.0, 18.0, 19.0, 16.0, after],
        "NVX": [100.0, 90.0, 95.0, 50.0, after],
    }
    return pd.DataFrame(
        {
            "symbol": [s for s in closes for _ in dates],
            "date": [d for _ in closes for d in dates],
            "close": [c for values in closes.values() for c in values],
        }
    )


PICKS = pd.DataFrame(
    {"symbol": ["AAA", "BBB"], "score": [9.0, 6.0], "weight": [0.6, 0.4]}
)


def test_prepare_buy_list_ignores_later_prices() -> None:
    low = buying.prepare_buy_list(_prices(after=1.0), PICKS, END, SETTINGS, 20.0)
    high = buying.prepare_buy_list(_prices(after=1000.0), PICKS, END, SETTINGS, 20.0)
    for first, second in zip(low, high, strict=True):
        pd.testing.assert_frame_equal(first, second)
    orders, _, trends = low
    assert trends["date"].max() == END
    # The last close on or before END: AAA 13, BBB 16, NVX 50.
    assert orders["close"].tolist() == [13.0, 16.0, 50.0]


def test_prepare_buy_list_adds_the_fixed_companies_outside_the_model() -> None:
    orders, states, _ = buying.prepare_buy_list(
        _prices(after=1.0), PICKS, END, SETTINGS, 20.0
    )
    assert orders["symbol"].tolist() == ["AAA", "BBB", "NVX"]
    assert orders["choice"].iloc[-1] == OWN
    assert states["symbol"].tolist() == ["AAA", "BBB", "NVX"]
    # NVX: 300 / 20 = 15 USD at 50 = 0.3 shares.
    assert orders["score_shares"].iloc[-1] == pytest.approx(0.3)
    # in_range comes from the trend states: NVX's last 3 are 90, 95, 50 -> 0.
    assert orders["in_range"].iloc[-1] == 0.0


def test_prepare_buy_list_company_without_a_close_has_no_shares() -> None:
    orders, states, _ = buying.prepare_buy_list(
        _prices(after=1.0), PICKS, END, {**SETTINGS, "fixed": {"ZZZ": 300.0}}, 20.0
    )
    assert "ZZZ" not in states["symbol"].tolist()
    zzz = orders.set_index("symbol").loc["ZZZ"]
    assert np.isnan(zzz["in_range"])
    assert np.isnan(zzz["score_shares"])


def test_prepare_buy_list_too_short_a_history_raises() -> None:
    with pytest.raises(IndexError):
        buying.prepare_buy_list(
            _prices(after=1.0), PICKS, END, {**SETTINGS, "lag_days": 4}, 20.0
        )


def test_prepare_buy_list_does_not_mutate_its_inputs() -> None:
    prices = _prices(after=1.0)
    before = prices.copy()
    picks = PICKS.copy()
    buying.prepare_buy_list(prices, picks, END, SETTINGS, 20.0)
    pd.testing.assert_frame_equal(prices, before)
    pd.testing.assert_frame_equal(picks, PICKS)
