"""Valuation-spread diagnostic, as fixed in design.md. Usage: run.py <library_snapshot_dir>"""

import io
import sys
import zipfile

import numpy as np
import pandas as pd

lib = sys.argv[1]
LAG, PCT, H, COST, BLOCK, DRAWS = 3, 0.20, 36, 0.005, 36, 2000
rng = np.random.default_rng(20261122)

# --- Shiller --------------------------------------------------------------------
raw = pd.read_excel(
    f"{lib}/data/shiller_ie_data.xls", sheet_name="Data", header=None, skiprows=8
)
raw = raw[pd.to_numeric(raw[0], errors="coerce").notna()]
d = pd.DataFrame(
    {
        "P": pd.to_numeric(raw[1], errors="coerce").values,
        "D": pd.to_numeric(raw[2], errors="coerce").values,
        "E": pd.to_numeric(raw[3], errors="coerce").values,
        "GS10": pd.to_numeric(raw[6], errors="coerce").values,
        "ECY": pd.to_numeric(raw[16], errors="coerce").values,
    },
    index=pd.PeriodIndex(
        [f"{int(x)}-{round((x - int(x)) * 100):02d}" for x in raw[0].astype(float)],
        freq="M",
    ),
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
    elif rows and len(parts) >= 1 and parts[0].isdigit() and len(parts[0]) == 4:
        break  # annual section starts
rf = pd.Series(dict(rows))
rf.index = pd.PeriodIndex([f"{k[:4]}-{k[4:]}" for k in rf.index], freq="M")
d["RF"] = rf

# --- Signal and returns ------------------------------------------------------------
d["EY"] = d["E"].shift(LAG) / d["P"]
d["S_main"] = d["EY"] - d["GS10"] / 100
d["S_ecy"] = d["ECY"].shift(LAG)
d["R"] = (d["P"].shift(-1) + d["D"].ffill() / 12) / d["P"] - 1  # return over t -> t+1


def evaluate(sig: str) -> dict:
    s = d[sig]
    thr = s.expanding(min_periods=120).quantile(PCT)
    inmkt = (s >= thr).astype(float).where(s.notna() & thr.notna())
    t = d.loc["1926-07":].copy()
    t["in"] = inmkt.loc[t.index]
    t = t.dropna(subset=["R", "RF", "in"])
    switch = t["in"].diff().abs().fillna(0)
    t["r_rule"] = t["in"] * t["R"] + (1 - t["in"]) * t["RF"] - switch * COST
    t["r_bh"] = t["R"]
    out = {"period": f"{t.index[0]}..{t.index[-1]}", "months": len(t)}
    for k in ("r_rule", "r_bh"):
        w = (1 + t[k]).cumprod()
        yrs = len(t) / 12
        out[k] = {
            "cagr": w.iloc[-1] ** (1 / yrs) - 1,
            "vol": t[k].std() * np.sqrt(12),
            "maxdd": (w / w.cummax() - 1).min(),
            "growth_of_1": w.iloc[-1],
        }
    out["cash_share"] = 1 - t["in"].mean()
    out["switches"] = int(switch.sum())
    # rolling 36m paired difference, annualised
    roll = (
        lambda r: (1 + r).rolling(H).apply(np.prod, raw=True) ** (12 / H) - 1
    )  # noqa: E731
    diff = (roll(t["r_rule"]) - roll(t["r_bh"])).dropna()
    out["diff36_mean"] = diff.mean()
    # moving-block bootstrap of the monthly paired difference, annualised mean
    m = (t["r_rule"] - t["r_bh"]).values
    n = len(m)
    nb = int(np.ceil(n / BLOCK))
    means = np.empty(DRAWS)
    for i in range(DRAWS):
        starts = rng.integers(0, n - BLOCK, nb)
        means[i] = np.concatenate([m[s0 : s0 + BLOCK] for s0 in starts])[:n].mean() * 12
    out["diff_ann"] = m.mean() * 12
    out["band90"] = (np.quantile(means, 0.05), np.quantile(means, 0.95))
    # exit episodes
    ep, cur = [], None
    for p, v in t["in"].items():
        if v == 0 and cur is None:
            cur = p
        if v == 1 and cur is not None:
            ep.append((str(cur), str(p - 1)))
            cur = None
    if cur is not None:
        ep.append((str(cur), "now"))
    out["exits"] = ep
    # out-of-sample R^2 for the next-36m excess return (Campbell-Thompson)
    ex = (1 + t["R"]).rolling(H).apply(np.prod, raw=True).shift(-H + 1) - (
        1 + t["RF"]
    ).rolling(H).apply(np.prod, raw=True).shift(-H + 1)
    df = pd.DataFrame({"y": ex, "x": s.loc[t.index]}).dropna()
    errs_m, errs_h = [], []
    for i in range(240, len(df)):
        train = df.iloc[: i - H + 1]  # windows closed by the forecast date
        if len(train) < 120:
            continue
        b = np.polyfit(train["x"], train["y"], 1)
        f_m = np.polyval(b, df["x"].iloc[i])
        f_h = train["y"].mean()
        errs_m.append((df["y"].iloc[i] - f_m) ** 2)
        errs_h.append((df["y"].iloc[i] - f_h) ** 2)
    out["oos_r2"] = 1 - np.sum(errs_m) / np.sum(errs_h)
    out["oos_n"] = len(errs_m)
    out["full_corr"] = df["x"].corr(df["y"])
    last = s.dropna()
    out["now"] = (
        str(last.index[-1]),
        last.iloc[-1],
        (s.dropna() <= last.iloc[-1]).mean(),
    )
    out["thr_now"] = thr.dropna().iloc[-1]
    return out


for sig in ("S_main", "S_ecy"):
    o = evaluate(sig)
    print(f"\n=== {sig}  {o['period']}  ({o['months']} months)")
    for k in ("r_rule", "r_bh"):
        v = o[k]
        print(
            f"  {k:7} CAGR {v['cagr']:6.2%}  vol {v['vol']:6.2%}  maxDD {v['maxdd']:7.2%}"
            f"  $1 -> {v['growth_of_1']:,.0f}"
        )
    print(f"  in cash {o['cash_share']:.1%} of months; {o['switches']} switches")
    print(
        f"  paired difference {o['diff_ann']:+.2%}/yr, 90% band {o['band90'][0]:+.2%} .. "
        f"{o['band90'][1]:+.2%}; rolling-36m mean {o['diff36_mean']:+.2%}/yr"
    )
    print(
        f"  predictive: OOS R^2 {o['oos_r2']:+.3f} over {o['oos_n']} forecasts;"
        f" full-sample corr {o['full_corr']:+.2f}"
    )
    print(
        f"  now ({o['now'][0]}): spread {o['now'][1]:+.2%}, percentile {o['now'][2]:.0%};"
        f" exit threshold {o['thr_now']:+.2%}"
    )
    print("  cash episodes:", "; ".join(f"{a}..{b}" for a, b in o["exits"]))
