"""Trend rules on technology and Nvidia, as fixed in design.md, "Second test".

Usage (repository root):
``.venv/bin/python Toolbox/SandBox/trend_following/run_tech.py data/interim/trend_tech/2026-11-22 data/raw/library/2026-11-22``
"""

import sys
import zipfile

import numpy as np
import pandas as pd

prices_dir, lib = sys.argv[1], sys.argv[2]
COST, BLOCK, DRAWS = 0.005, 36, 2000
rng = np.random.default_rng(20261122)
FALLS = {
    "2000-02": ("2000-04", "2002-09"),
    "2007-09": ("2007-11", "2009-02"),
    "2020": ("2020-02", "2020-03"),
    "2022": ("2022-01", "2022-12"),
}

p = pd.read_parquet(f"{prices_dir}/prices.parquet")
p["month"] = pd.to_datetime(p["date"]).dt.to_period("M")
monthly = (
    p.sort_values("date").groupby(["symbol", "month"])["adj_close"].last().unstack(0)
)

with zipfile.ZipFile(f"{lib}/data/ff_research_factors_monthly.zip") as z:
    txt = z.read(z.namelist()[0]).decode("latin1")
rows = []
for line in txt.splitlines():
    parts = [x.strip() for x in line.split(",")]
    if len(parts) == 5 and parts[0].isdigit() and len(parts[0]) == 6:
        rows.append((parts[0], float(parts[4]) / 100))
    elif rows and parts and parts[0].isdigit() and len(parts[0]) == 4:
        break
rf = pd.Series(dict(rows))
rf.index = pd.PeriodIndex([f"{k[:4]}-{k[4:]}" for k in rf.index], freq="M")


def compare(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a > b).astype(float).where(a.notna() & b.notna())


def stats(r: pd.Series) -> tuple[float, float, float]:
    w = (1 + r).cumprod()
    return (
        w.iloc[-1] ** (12 / len(r)) - 1,
        r.std() * np.sqrt(12),
        (w / w.cummax() - 1).min(),
    )


for sym in ["QQQ", "XLK", "NVDA", "SPY"]:
    px = monthly[sym].dropna()
    d = pd.DataFrame({"P": px})
    d["RF"] = rf
    d["R"] = d["P"].shift(-1) / d["P"] - 1  # month t -> t+1, dividends in adj_close
    past = d["P"] / d["P"].shift(12)
    rf12 = (1 + d["RF"].shift(1)).rolling(12).apply(np.prod, raw=True)
    sig = {
        "A_ma10": compare(d["P"], d["P"].rolling(10).mean()),
        "B_tsmom12": compare(past, rf12),
    }
    print(f"\n######## {sym}{'  (control)' if sym == 'SPY' else ''}")
    for name, s in sig.items():
        t = d.assign(inn=s).dropna(subset=["R", "RF", "inn"])
        sw = t["inn"].diff().abs().fillna(0)
        t["rule"] = t["inn"] * t["R"] + (1 - t["inn"]) * t["RF"] - sw * COST
        (cr, vr, mr), (ci, vi, mi) = stats(t["rule"]), stats(t["R"])
        m = (t["rule"] - t["R"]).values
        n, nb = len(m), int(np.ceil(len(m) / BLOCK))
        boots = [
            np.concatenate([m[a : a + BLOCK] for a in rng.integers(0, n - BLOCK, nb)])[
                :n
            ].mean()
            * 12
            for _ in range(DRAWS)
        ]
        falls = "; ".join(
            f"{k} {(1 + t.loc[a:b, 'rule']).prod() - 1:+.0%}/{(1 + t.loc[a:b, 'R']).prod() - 1:+.0%}"
            for k, (a, b) in FALLS.items()
            if len(t.loc[a:b])
        )
        now = s.dropna()
        print(
            f"  {name:9} {t.index[0]}..{t.index[-1]}: rule {cr:6.1%} vol {vr:5.1%} maxDD {mr:6.1%}"
            f" | hold {ci:6.1%} vol {vi:5.1%} maxDD {mi:6.1%} | cash {1 - t['inn'].mean():4.0%},"
            f" {int(sw.sum())} switches"
        )
        print(
            f"            paired {m.mean() * 12:+.1%}/yr (90% {np.quantile(boots, .05):+.1%}"
            f" .. {np.quantile(boots, .95):+.1%}); falls rule/hold: {falls}"
        )
        print(
            f"            latest signal ({now.index[-1]}): {'IN' if now.iloc[-1] else 'CASH'}"
        )
