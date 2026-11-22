"""Shared inputs for the SandBox diagnostics: Shiller's data, the T-bill rate, the bootstrap.

Exploratory code outside the standard. One place for what the valuation-spread and
trend-following diagnostics share, so a fix lands in all of them (Warden, VI_202611_005).

Timing conventions
------------------
- Shiller's price ``P_t`` is the average of month t's daily closes, known at the end of
  month t. His return ``R_t = (P_{t+1} + D_t / 12) / P_t - 1`` runs from mid-month t to
  mid-month t+1, so a signal computed from ``P_t`` may only trade ``R_{t+1}`` (from
  mid-month t+1): ``position_for_return(signal)`` shifts it one month.
- Cash over that return earns about half of month t+1's T-bill and half of month t+2's:
  ``cash_for_shiller_return``.
- Month-end closes (Yahoo) have no overlap: a signal at the close of month t trades the
  return over month t+1, which earns month t+1's T-bill (``rf.shift(-1)``).
"""

import zipfile

import numpy as np
import pandas as pd

LAST_COMPLETE_MONTH = "2026-10"  # snapshot 2026-11-22: November is partial
TEST_END = "2026-09"  # last return month whose end price is a complete month
FALLS = {  # months in which the return is earned, fixed in the designs
    "1929-32": ("1929-09", "1932-06"),
    "1937-38": ("1937-03", "1938-03"),
    "1973-74": ("1973-01", "1974-09"),
    "2000-02": ("2000-04", "2002-09"),
    "2007-09": ("2007-11", "2009-02"),
    "2020": ("2020-02", "2020-03"),
    "2022": ("2022-01", "2022-09"),
}


def load_shiller(lib: str) -> pd.DataFrame:
    """Shiller's monthly table: P, D, E, GS10 (percent) and ECY, by month, complete months only."""
    raw = pd.read_excel(
        f"{lib}/data/shiller_ie_data.xls", sheet_name="Data", header=None, skiprows=8
    )
    raw = raw[pd.to_numeric(raw[0], errors="coerce").notna()]
    idx = pd.PeriodIndex(
        [f"{int(x)}-{round((x - int(x)) * 100):02d}" for x in raw[0].astype(float)],
        freq="M",
    )
    cols = {"P": 1, "D": 2, "E": 3, "GS10": 6, "ECY": 16}
    d = pd.DataFrame(
        {k: pd.to_numeric(raw[c], errors="coerce").values for k, c in cols.items()},
        index=idx,
    )
    return d[~d.index.duplicated()].loc[:LAST_COMPLETE_MONTH]


def load_rf(lib: str) -> pd.Series:
    """Fama-French monthly risk-free rate (1-month T-bill), as a fraction, by month."""
    with zipfile.ZipFile(f"{lib}/data/ff_research_factors_monthly.zip") as z:
        txt = z.read(z.namelist()[0]).decode("latin1")
    rows = []
    for line in txt.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 5 and parts[0].isdigit() and len(parts[0]) == 6:
            rows.append((parts[0], float(parts[4]) / 100))
        elif rows and parts and parts[0].isdigit() and len(parts[0]) == 4:
            break  # the annual section starts
    rf = pd.Series(dict(rows))
    rf.index = pd.PeriodIndex([f"{k[:4]}-{k[4:]}" for k in rf.index], freq="M")
    return rf


def shiller_return(d: pd.DataFrame) -> pd.Series:
    """``R_t``: mid-month t to mid-month t+1, dividends at D_t / 12.

    Missing recent dividends are carried forward (a stated bias, not a silent fill).
    """
    return (d["P"].shift(-1) + d["D"].ffill() / 12) / d["P"] - 1


def position_for_return(signal: pd.Series) -> pd.Series:
    """The position for ``R_t`` is the signal known at the end of month t-1."""
    return signal.shift(1)


def cash_for_shiller_return(rf: pd.Series, index: pd.PeriodIndex) -> pd.Series:
    """T-bill return over mid-month t to mid-month t+1: the mean of RF_t and RF_{t+1}."""
    r = rf.reindex(index)
    return (r + r.shift(-1)) / 2


def compare(a: pd.Series, b: pd.Series) -> pd.Series:
    """1.0 where a > b, 0.0 where not, NaN where either is missing (never read as cash)."""
    return (a > b).astype(float).where(a.notna() & b.notna())


def block_bootstrap(
    m: np.ndarray, block: int, draws: int, rng: np.random.Generator
) -> np.ndarray:
    """Annualised means of moving-block resamples of the monthly series ``m``."""
    n = len(m)
    nb = int(np.ceil(n / block))
    out = np.empty(draws)
    for i in range(draws):
        starts = rng.integers(0, n - block + 1, nb)  # the last block can be drawn
        out[i] = np.concatenate([m[s : s + block] for s in starts])[:n].mean() * 12
    return out


def summary(r: pd.Series) -> tuple[float, float, float]:
    """Compound annual return, annualised volatility and maximum drawdown of monthly returns."""
    w = (1 + r).cumprod()
    return (
        float(w.iloc[-1] ** (12 / len(r)) - 1),
        float(r.std() * np.sqrt(12)),
        float((w / w.cummax() - 1).min()),
    )


def falls(rule: pd.Series, hold: pd.Series) -> str:
    """Rule and holding returns over each fall, by the month the return is earned."""
    out = []
    for label, (a, b) in FALLS.items():
        h = rule.loc[a:b]
        if len(h):
            r1 = (1 + h).prod() - 1
            r2 = (1 + hold.loc[a:b]).prod() - 1
            out.append(f"{label} {r1:+.0%}/{r2:+.0%}")
    return "; ".join(out)
