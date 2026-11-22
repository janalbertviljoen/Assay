# VI_202611_005: Strategy library and two market diagnostics

| Field | Value |
|---|---|
| Status | done, 2026-11-22 |
| Priority | medium |
| Kind | tooling |
| Depends on | none |
| Branch | `feature/value-investing/analysis-2026-11-22` |
| Raised | 2026-11-22 |

## Description

The user wanted a basis for analysing other strategies: a library of trading-strategy
texts, papers and long-history data, and tests of when to step out of the market
(valuation spread, trend following). Exploratory work in `Toolbox/SandBox/`, outside the
standard; the results are diagnostics, not adopted methodology.

## Outcome

Closed 2026-11-22. The Warden ran once, on 2026-11-22 at commit a57e7f5: no blocking
findings, eight to fix and nine notes, all fixed or answered before the merge. No
inspections ran (one session, records and SandBox code).

**Conclusion.** Neither sell rule is adopted. A valuation spread gave no timing edge over
a century; trend following roughly halves the worst fall but costs return on the S&P 500
and costs clearly on a single share (Nvidia). The library and the fetch tools stay as the
basis for the next strategy studies.

**Library.** A dated, git-ignored snapshot (`data/raw/library/2026-11-22/`, manifest with
licence, URL and SHA-256): 20 legally free items. Classic texts (Hamilton 1922, Bachelier
1900); papers on equity-premium prediction, factors (value, momentum, quality, low beta,
Buffett's Alpha), trend following and multiple testing; long-history data (Shiller since
1871, Damodaran since 1960, Fama-French since 1926). Text extracted with `pypdf`. Six
Gutenberg books and one AMS paper remain to fetch (`still_to_fetch.tsv`; the sandbox proxy
refuses those hosts). Fetch tools in `Toolbox/SandBox/strategy_library/`, with shared
inputs in `series.py`. MSCI index factsheets in `data/raw/index_sheets/`. The owner's fund
list and fact sheets stay in `~/Documents/Personal/Finances/fund_sheets/`, never here.

**Designs.** `Toolbox/SandBox/valuation_spread/design.md` and
`Toolbox/SandBox/trend_following/design.md`, each fixed before its run and amended after
the Warden's review (timing, months, control, falls), with the amendments marked as such.

**Results** (detail in `midas/toolbox/value_investing/notes.md`: "Valuation spread as a
sell-everything signal", "Trend following as the sell rule", "Market valuations by region").

- Valuation spread, returns 1926-07 to 2026-08: the nominal spread cost $2.64\%$ a year
  (90% band $-4.54\%$ to $-0.53\%$); Shiller's excess CAPE yield gave no difference
  ($-0.19\%$, band $-1.52\%$ to $+1.09\%$), a smaller worst fall ($-71\%$ against $-82\%$)
  and an out-of-sample $R^2$ of $+0.017$.
- Trend following on the S&P 500: rule A (10-month average) $-1.72\%$ a year (band $-3.34\%$
  to $+0.12\%$), rule B (12-month momentum) $-2.25\%$ ($-4.00\%$ to $-0.36\%$); worst fall
  about $-50\%$ against $-82\%$.
- Trend following on technology, month-end closes from about 2000: no reliable gain on QQQ
  or XLK, worst fall roughly halved; on Nvidia rule B cost $12.2\%$ a year (band $-20.7\%$ to
  $-6.1\%$).
- Count: ten specifications (two valuation, two S&P trend, six technology; the SPY control
  not counted). The bands are not adjusted for this multiple testing.
- Events (quant.md 14), as a hypothesis: from 2026-10-06 to 2026-11-20 the technology
  series fell 20–48% (Nvidia $-47.5\%$), which press reports attribute to an AI-led sell-off
  after the 3 November election and the departure of Nvidia's chief executive. At the
  October close every trend rule was in; the partial November is not a signal.

**The Warden's findings and what was done.**
1. Half-month look-ahead on Shiller's averaged prices: a signal now trades from the
   following month; rerun. It had made rule A look better than the index.
2. Partial November read as the current signal: complete months only, the partial month
   printed and labelled separately.
3. End date set by the T-bill file: fixed end months in `series.py` and the designs.
4. Control on longer dates: SPY starts at the latest first month of the technology series.
5. `sources.tsv` pointed at the stale Yale file: points at the file used; the manifest URL
   and SHA-256 match it.
6. `fetch.sh` could delete a good copy: temporary file then move, skips existing files,
   later passes into a new dated folder.
7. Stale records: the notes corrected (scripts' location, how `pypdf` was installed, how
   the MSCI figures were read: `extract_text.py`).
8. Evidence in the change file: this outcome links the designs and states the count, the
   multiple-testing caveat and the events.
9–15. T-bill alignment fixed in code; the bootstrap draws the last block; the dividend fill
   stated as a bias; events worded as a hypothesis; the falls fixed in the designs and
   shared; the lambda replaced by a function; the fact-sheet fetcher's header says what it
   overwrites. 16–17: no change needed (designs belong with the SandBox code).

**Decisions (user, 2026-11-22).** Private use relaxes what the library may hold, but not to
unauthorised copies of copyrighted books, which are bought; `xlrd` and `pypdf` in a
`library` dependency group; work reviewed as uncommitted changes before any commit;
commit, push and the Warden on the whole branch before closing.

**Alternatives not taken.** A partial tilt (less equity when expensive) rather than
all-or-nothing, and a trend rule tested inside a tax-free account only: both stay open in
the notes.
