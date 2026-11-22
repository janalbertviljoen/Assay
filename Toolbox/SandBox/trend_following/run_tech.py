"""Trend rules on technology and Nvidia, as fixed in design.md, "Second test".

Usage (repository root):
``.venv/bin/python -m Toolbox.SandBox.trend_following.run_tech data/interim/trend_tech/2026-11-22 data/raw/library/2026-11-22``

Month-end closes: a signal at the close of month t trades the return over month t+1,
which earns month t+1's T-bill. SPY, the control, runs on the same months as the
technology series (from their common start).
"""

import sys

import numpy as np
import pandas as pd

from Toolbox.SandBox.strategy_library.series import (
    LAST_COMPLETE_MONTH,
    TEST_END,
    block_bootstrap,
    compare,
    falls,
    load_rf,
    summary,
)

prices_dir, lib = sys.argv[1], sys.argv[2]
COST, BLOCK, DRAWS = 0.005, 36, 2000
TECH = ["QQQ", "XLK", "NVDA"]
rng = np.random.default_rng(20261122)

p = pd.read_parquet(f"{prices_dir}/prices.parquet")
p["date"] = pd.to_datetime(p["date"])
p["month"] = p["date"].dt.to_period("M")
monthly = (
    p.sort_values("date").groupby(["symbol", "month"])["adj_close"].last().unstack(0)
)
live = p.sort_values("date").groupby("symbol").tail(1).set_index("symbol")
monthly = monthly.loc[:LAST_COMPLETE_MONTH]  # complete months only
common_start = max(monthly[s].first_valid_index() for s in TECH)
rf = load_rf(lib)

for sym in [*TECH, "SPY"]:
    px = monthly[sym].dropna()
    if sym == "SPY":
        px = px.loc[common_start:]
    d = pd.DataFrame({"P": px})
    d["R"] = d["P"].shift(-1) / d["P"] - 1  # over month t+1; dividends in adj_close
    d["CASH"] = rf.reindex(d.index).shift(-1)  # month t+1's T-bill
    past = d["P"] / d["P"].shift(12)  # months t-11..t
    rf12 = (1 + rf.reindex(d.index)).rolling(12).apply(np.prod, raw=True)  # t-11..t
    ma10 = d["P"].rolling(10).mean()
    sig = {"A_ma10": compare(d["P"], ma10), "B_tsmom12": compare(past, rf12)}
    print(f"\n######## {sym}{'  (control, same months)' if sym == 'SPY' else ''}")
    for name, s in sig.items():
        t = d.assign(inn=s).loc[:TEST_END].dropna(subset=["R", "CASH", "inn"])
        sw = t["inn"].diff().abs().fillna(0)
        t["rule"] = t["inn"] * t["R"] + (1 - t["inn"]) * t["CASH"] - sw * COST
        (cr, vr, mr), (ci, vi, mi) = summary(t["rule"]), summary(t["R"])
        m = (t["rule"] - t["R"]).values
        b = block_bootstrap(m, BLOCK, DRAWS, rng)
        earned = t.set_axis(t.index + 1)  # the month each return is earned
        print(
            f"  {name:9} returns {earned.index[0]}..{earned.index[-1]}: rule {cr:6.1%}"
            f" vol {vr:5.1%} maxDD {mr:6.1%} | hold {ci:6.1%} vol {vi:5.1%} maxDD {mi:6.1%}"
            f" | cash {1 - t['inn'].mean():4.0%}, {int(sw.sum())} switches"
        )
        print(
            f"            paired {m.mean() * 12:+.1%}/yr (90% {np.quantile(b, .05):+.1%}"
            f" .. {np.quantile(b, .95):+.1%}); falls rule/hold:"
            f" {falls(earned['rule'], earned['R'])}"
        )
        last = s.dropna()
        print(
            f"            signal at the {last.index[-1]} close: "
            f"{'IN' if last.iloc[-1] else 'CASH'}"
        )
    row = live.loc[sym]
    print(
        f"  partial month, not a signal: close {row['adj_close']:.2f} on"
        f" {row['date']:%Y-%m-%d} is {row['adj_close'] / ma10.iloc[-1] - 1:+.1%}"
        f" against the 10-month average to {LAST_COMPLETE_MONTH}"
    )
