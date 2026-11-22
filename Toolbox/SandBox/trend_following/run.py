"""Trend-following diagnostic, as fixed in design.md. Usage: run.py <library_snapshot_dir>"""

import sys
import zipfile

import numpy as np
import pandas as pd

lib = sys.argv[1]
COST, BLOCK, DRAWS = 0.005, 36, 2000
rng = np.random.default_rng(20261122)
CRASHES = {
    "1929-32": ("1929-08", "1932-06"),
    "1937-38": ("1937-02", "1938-03"),
    "1973-74": ("1973-01", "1974-09"),
    "2000-02": ("2000-08", "2002-09"),
    "2007-09": ("2007-10", "2009-02"),
    "2020": ("2020-01", "2020-03"),
    "2022": ("2021-12", "2022-09"),
}

# --- Shiller ------------------------------------------------------------------------
raw = pd.read_excel(
    f"{lib}/data/shiller_ie_data.xls", sheet_name="Data", header=None, skiprows=8
)
raw = raw[pd.to_numeric(raw[0], errors="coerce").notna()]
idx = pd.PeriodIndex(
    [f"{int(x)}-{round((x - int(x)) * 100):02d}" for x in raw[0].astype(float)],
    freq="M",
)
d = pd.DataFrame(
    {
        "P": pd.to_numeric(raw[1], errors="coerce").values,
        "D": pd.to_numeric(raw[2], errors="coerce").values,
    },
    index=idx,
)
d = d[~d.index.duplicated()]

# --- Fama-French RF -----------------------------------------------------------------
with zipfile.ZipFile(f"{lib}/data/ff_research_factors_monthly.zip") as z:
    txt = z.read(z.namelist()[0]).decode("latin1")
rows = []
for line in txt.splitlines():
    parts = [p.strip() for p in line.split(",")]
    if len(parts) == 5 and parts[0].isdigit() and len(parts[0]) == 6:
        rows.append((parts[0], float(parts[4]) / 100))
    elif rows and parts and parts[0].isdigit() and len(parts[0]) == 4:
        break
rf = pd.Series(dict(rows))
rf.index = pd.PeriodIndex([f"{k[:4]}-{k[4:]}" for k in rf.index], freq="M")
d["RF"] = rf

# Return over month t -> t+1, and the return earned in month t (for the 12-month signal).
d["R"] = (d["P"].shift(-1) + d["D"].ffill() / 12) / d["P"] - 1
d["R_past"] = d["R"].shift(1)  # return earned over t-1 -> t, known at t


def compare(a: pd.Series, b: pd.Series) -> pd.Series:
    """1.0 where a > b, 0.0 where not, NaN where either input is missing (never 'cash')."""
    return (a > b).astype(float).where(a.notna() & b.notna())


ma10 = d["P"].rolling(10).mean()
eq12 = (1 + d["R_past"]).rolling(12).apply(np.prod, raw=True)
rf12 = (1 + d["RF"].shift(1)).rolling(12).apply(np.prod, raw=True)
signals = {"A_ma10": compare(d["P"], ma10), "B_tsmom12": compare(eq12, rf12)}


def stats(r: pd.Series) -> dict:
    w = (1 + r).cumprod()
    return {
        "cagr": w.iloc[-1] ** (12 / len(r)) - 1,
        "vol": r.std() * np.sqrt(12),
        "maxdd": (w / w.cummax() - 1).min(),
    }


def evaluate(name: str) -> None:
    t = d.loc["1926-07":].copy()
    t["in"] = signals[name].loc[t.index]
    t = t.dropna(subset=["R", "RF", "in"])
    sw = t["in"].diff().abs().fillna(0)
    t["rule"] = t["in"] * t["R"] + (1 - t["in"]) * t["RF"] - sw * COST
    print(f"\n=== {name}  {t.index[0]}..{t.index[-1]}  ({len(t)} months)")
    for k in ("rule", "R"):
        s = stats(t[k])
        label = "rule" if k == "rule" else "index"
        print(
            f"  {label:5} CAGR {s['cagr']:6.2%}  vol {s['vol']:6.2%}  maxDD {s['maxdd']:7.2%}"
        )
    print(f"  in cash {1 - t['in'].mean():.1%} of months; {int(sw.sum())} switches")
    m = (t["rule"] - t["R"]).values
    n, nb = len(m), int(np.ceil(len(m) / BLOCK))
    boots = np.array(
        [
            np.concatenate([m[s : s + BLOCK] for s in rng.integers(0, n - BLOCK, nb)])[
                :n
            ].mean()
            * 12
            for _ in range(DRAWS)
        ]
    )
    print(
        f"  paired difference {m.mean() * 12:+.2%}/yr, 90% band "
        f"{np.quantile(boots, 0.05):+.2%} .. {np.quantile(boots, 0.95):+.2%}"
    )
    for a, b in (("1926-07", "1975-12"), ("1976-01", None)):
        h = t.loc[a:b] if b else t.loc[a:]
        sr, si = stats(h["rule"]), stats(h["R"])
        print(
            f"  half {h.index[0]}..{h.index[-1]}: rule {sr['cagr']:6.2%} (maxDD {sr['maxdd']:7.2%})"
            f" vs index {si['cagr']:6.2%} (maxDD {si['maxdd']:7.2%})"
        )
    cr = []
    for lab, (a, b) in CRASHES.items():
        h = t.loc[a:b]
        if len(h):
            cr.append(
                f"{lab}: {(1 + h['rule']).prod() - 1:+.0%} vs {(1 + h['R']).prod() - 1:+.0%}"
            )
    print("  falls (rule vs index):", "; ".join(cr))
    last = signals[name].dropna()
    print(
        f"  latest computable signal ({last.index[-1]}): "
        f"{'IN the index' if last.iloc[-1] else 'in CASH'}"
    )
    if name == "A_ma10":
        print(
            f"    price {d['P'].iloc[-1]:,.0f} vs 10-month average {ma10.iloc[-1]:,.0f}"
        )
    else:
        print(
            f"    12-month index return to {eq12.dropna().index[-1]}: {eq12.dropna().iloc[-1] - 1:+.1%}"
            f" vs T-bills {rf12.dropna().iloc[-1] - 1:+.1%} (to {rf12.dropna().index[-1]})"
        )


for sig in signals:
    evaluate(sig)
