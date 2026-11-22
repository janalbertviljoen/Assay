"""Valuation-spread diagnostic on Shiller's S&P 500, as fixed in design.md.

Usage (repository root):
``.venv/bin/python -m Toolbox.SandBox.valuation_spread.run data/raw/library/2026-11-22``
"""

import sys

import numpy as np
import pandas as pd

from Toolbox.SandBox.strategy_library.series import (
    TEST_END,
    block_bootstrap,
    cash_for_shiller_return,
    load_rf,
    load_shiller,
    position_for_return,
    shiller_return,
    summary,
)

lib = sys.argv[1]
LAG, PCT, H, COST, BLOCK, DRAWS = 3, 0.20, 36, 0.005, 36, 2000
rng = np.random.default_rng(20261122)

d = load_shiller(lib)
d["R"] = shiller_return(d)
d["CASH"] = cash_for_shiller_return(load_rf(lib), d.index)
d["S_main"] = d["E"].shift(LAG) / d["P"] - d["GS10"] / 100
d["S_ecy"] = d["ECY"].shift(LAG)


def growth(r: pd.Series) -> pd.Series:
    """Growth of 1 over the next H returns, R_{t+1}..R_{t+H} (the returns a signal at t trades)."""
    return (1 + r).rolling(H).apply(np.prod, raw=True).shift(-H)


def evaluate(sig: str) -> None:
    s = d[sig]
    thr = s.expanding(min_periods=120).quantile(PCT)
    signal = (s >= thr).astype(float).where(s.notna() & thr.notna())
    t = d.loc["1926-07":TEST_END].copy()
    t["in"] = position_for_return(signal).loc[t.index]
    t = t.dropna(subset=["R", "CASH", "in"])
    sw = t["in"].diff().abs().fillna(0)
    t["rule"] = t["in"] * t["R"] + (1 - t["in"]) * t["CASH"] - sw * COST
    print(f"\n=== {sig}  returns {t.index[0]}..{t.index[-1]}  ({len(t)} months)")
    for k, label in (("rule", "rule"), ("R", "hold")):
        c, v, m = summary(t[k])
        print(f"  {label:4} CAGR {c:6.2%}  vol {v:6.2%}  maxDD {m:7.2%}")
    print(f"  in cash {1 - t['in'].mean():.1%} of months; {int(sw.sum())} switches")
    m = (t["rule"] - t["R"]).values
    b = block_bootstrap(m, BLOCK, DRAWS, rng)
    print(
        f"  paired difference {m.mean() * 12:+.2%}/yr, 90% band "
        f"{np.quantile(b, 0.05):+.2%} .. {np.quantile(b, 0.95):+.2%}"
    )
    # Out-of-sample R^2 (Campbell-Thompson) for the excess return over the next H months.
    span = d.loc["1926-07":TEST_END]
    y = growth(span["R"]) - growth(span["CASH"])
    df = pd.DataFrame({"y": y, "x": s.loc[span.index]}).dropna()
    err_m, err_h = [], []
    for i in range(240, len(df)):
        train = df.iloc[
            : i - H
        ]  # targets whose H months had closed by the forecast date
        if len(train) < 120:
            continue
        coef = np.polyfit(train["x"], train["y"], 1)
        err_m.append((df["y"].iloc[i] - np.polyval(coef, df["x"].iloc[i])) ** 2)
        err_h.append((df["y"].iloc[i] - train["y"].mean()) ** 2)
    print(
        f"  predictive: OOS R^2 {1 - np.sum(err_m) / np.sum(err_h):+.3f} over {len(err_m)}"
        f" forecasts; full-sample corr {df['x'].corr(df['y']):+.2f}"
    )
    last = s.dropna()
    print(
        f"  latest complete month ({last.index[-1]}): spread {last.iloc[-1]:+.2%},"
        f" percentile {(last <= last.iloc[-1]).mean():.0%}; exit line {thr.dropna().iloc[-1]:+.2%}"
    )
    ep, cur = [], None
    for p, v in t["in"].items():
        if v == 0 and cur is None:
            cur = p
        if v == 1 and cur is not None:
            ep.append(f"{cur}..{p - 1}")
            cur = None
    if cur is not None:
        ep.append(f"{cur}..end")
    print("  cash periods (return months):", "; ".join(ep))


for name in ("S_main", "S_ecy"):
    evaluate(name)
