"""Synthetic inputs for the steward's tests; no figure comes from data/private/."""

import tomllib
from pathlib import Path
from typing import Any

import pandas as pd

from Toolbox.value_investing.buy_list import buy_list
from Toolbox.value_investing.report import BuyList, BuyReport

REPO = Path(__file__).resolve().parents[2]

# Hand-checked: bond_payment = 1100 - 50 - 50 = 1000 a month, so the bond of 18 000 at
# 0% is repaid after 18 months; the net worth is 1000 + 100 x 20 + 3000 + (20 000 + 500
# - 18 000) + 2000 - 1800 = 8700 at 20 ZAR per USD.
FINANCES_TOML = """
as_of = 2026-11-01

[[accounts]]
name = "Fund A"
kind = "listed"
value = 1000.0
monthly = 100.0

[[accounts]]
name = "Fund B"
kind = "listed"
value = 100.0
currency = "USD"

[[accounts]]
name = "Pension"
kind = "retirement"
value = 3000.0
growth = 0.1

[property]
name = "PropCo"
value = 20000.0
cost = 15000.0
other_assets = 500.0
bond = 18000.0
bond_note = "a synthetic bond"
rate = 0.0
members_loan = 4000.0
years = 1
horizons = [1]
growth = { low = 0.0, high = 0.1 }
monthly = { paid_by_user = 1100.0, bond_instalment = 600.0, levies = 50.0, property_rates = 50.0 }

[targets]
X = 30.0
Y = 30.0
Z = 20.0

[holdings]
X = 500.0
Y = 300.0
Z = 200.0

[car]
value = 2000.0
loan = 1800.0
rate = 0.0
payment = 500.0
insurance = 100.0

[person]
age = 60
retirement_age = 62
inflation = 0.1

[tfsa]
contributed = 100000.0
lifetime_limit = 500000.0
annual_limit = 36000.0

[buy_list]
currency = "ZAR"
picks_amount = 5000.0
fixed = { NVX = 1000.0 }
"""


def make_buy_report(folder: Path, *, rate: float = 20.0) -> BuyReport:
    """A synthetic buy report of two picks and one fixed purchase, in rand."""
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
    orders = buy_list(
        picks,
        pd.Series({"AAA": 10.0, "BBB": 20.0, "NVX": 100.0}),
        pd.Series({"AAA": 0.5, "BBB": 0.1, "NVX": 0.3}),
        rate=rate,
        picks_amount=5000.0,
        ramp=(3.0, 1.0),
        blend=(2.0, 1.0),
        fixed={"NVX": 1000.0},
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
    settings = {
        "currency": "ZAR",
        "rank_ramp": [3.0, 1.0],
        "blend": [2.0, 1.0],
        "trend_days": 200,
        "slide": 0.2,
        "years": 5,
        "slope_years": 2,
        "range_days": 1260,
        "high_days": 252,
        "lag_days": 21,
        "rate": rate,
        "rate_date": pd.Timestamp("2026-11-19"),
    }
    return BuyReport(
        buy=BuyList(orders, states, settings, folder / "trends.png"),
        next_picks=picks,
        names={"AAA": "Alpha Corp", "NVX": "Nova Inc"},
        index_label="AAA 100",
        sectors={"Energy": "energy"},
        prices_figure=folder / "next_prices.png",
        pick_years=3,
        pick_scenario=2020,
    )


def value_text() -> dict[str, Any]:
    """The tracked value report text (no private text is read)."""
    with (REPO / "config" / "report_value_investing.toml").open("rb") as handle:
        return tomllib.load(handle)
