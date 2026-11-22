"""Trend-following diagnostic on Shiller's S&P 500, as fixed in design.md.

Usage (repository root):
``.venv/bin/python -m Toolbox.SandBox.trend_following.run data/raw/library/2026-11-22``
"""

import sys

import numpy as np

from Toolbox.SandBox.strategy_library.series import (
    TEST_END,
    block_bootstrap,
    cash_for_shiller_return,
    compare,
    falls,
    load_rf,
    load_shiller,
    position_for_return,
    shiller_return,
    summary,
)

lib = sys.argv[1]
COST, BLOCK, DRAWS = 0.005, 36, 2000
rng = np.random.default_rng(20261122)

d = load_shiller(lib)
d["R"] = shiller_return(d)
d["CASH"] = cash_for_shiller_return(load_rf(lib), d.index)
rf = load_rf(lib).reindex(d.index)

# R_t runs mid t to mid t+1; the 12 returns R_{t-12}..R_{t-1} span mid t-12 to mid t,
# known at the end of t, against the T-bills of months t-11..t.
eq12 = (1 + d["R"].shift(1)).rolling(12).apply(np.prod, raw=True)
rf12 = (1 + rf).rolling(12).apply(np.prod, raw=True)
ma10 = d["P"].rolling(10).mean()
signals = {"A_ma10": compare(d["P"], ma10), "B_tsmom12": compare(eq12, rf12)}


def evaluate(name: str) -> None:
    t = d.loc["1926-07":TEST_END].copy()
    t["in"] = position_for_return(signals[name]).loc[t.index]
    t = t.dropna(subset=["R", "CASH", "in"])
    sw = t["in"].diff().abs().fillna(0)
    t["rule"] = t["in"] * t["R"] + (1 - t["in"]) * t["CASH"] - sw * COST
    print(f"\n=== {name}  returns {t.index[0]}..{t.index[-1]}  ({len(t)} months)")
    for k, label in (("rule", "rule"), ("R", "index")):
        c, v, m = summary(t[k])
        print(f"  {label:5} CAGR {c:6.2%}  vol {v:6.2%}  maxDD {m:7.2%}")
    print(f"  in cash {1 - t['in'].mean():.1%} of months; {int(sw.sum())} switches")
    m = (t["rule"] - t["R"]).values
    b = block_bootstrap(m, BLOCK, DRAWS, rng)
    print(
        f"  paired difference {m.mean() * 12:+.2%}/yr, 90% band "
        f"{np.quantile(b, 0.05):+.2%} .. {np.quantile(b, 0.95):+.2%}"
    )
    for a, z in (("1926-07", "1975-12"), ("1976-01", TEST_END)):
        h = t.loc[a:z]
        (cr, _, mr), (ci, _, mi) = summary(h["rule"]), summary(h["R"])
        print(
            f"  half {h.index[0]}..{h.index[-1]}: rule {cr:6.2%} (maxDD {mr:7.2%})"
            f" vs index {ci:6.2%} (maxDD {mi:7.2%})"
        )
    # R_t is earned mostly in month t+1: index the falls by that month.
    earned = t.set_axis(t.index + 1)
    print("  falls (rule/index):", falls(earned["rule"], earned["R"]))
    last = signals[name].dropna()
    print(
        f"  latest complete-month signal ({last.index[-1]}, Shiller monthly average): "
        f"{'IN' if last.iloc[-1] else 'CASH'}"
    )


for sig in signals:
    evaluate(sig)
