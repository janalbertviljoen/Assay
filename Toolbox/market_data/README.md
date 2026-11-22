# market_data

Shared market data for every tool in this repository (`value_investing`, `hand_o_midas`):
the sources, the cleaned standard tables and the shared metrics, each owned once. Tools
read from here; they never fetch or clean data themselves. The package sits between
`skatkis` (domain-free infrastructure) and the tools.

## Data sources


Three free sources feed every tool, each through one module in `sources/`, and each
answers a different question. **EDGAR** says what a company reported and when;
**Yahoo** says what its shares traded at and what they paid out; **FRED** says what a
dollar was worth in rand. None of them can stand in for another: EDGAR has no market
prices, Yahoo's fundamentals are restated and short, and FRED has no company data.

| | SEC EDGAR | Yahoo Finance | FRED |
|---|---|---|---|
| Module | `sources/edgar.py`, `sources/tag_map.py` | `sources/prices.py` | `sources/fred.py` |
| Provides | Reported financial-statement values, per-share figures, share counts | Daily prices, dividends, splits; the S&P 500 total-return index `^SP500TR` | Daily USD/ZAR exchange rate (`DEXSFUS`) |
| Key | CIK (10-digit company number) | Ticker symbol in Yahoo's convention (`BRK-B`) | Series ID |
| Requested | Full documents (the API has no date filter); used from 2006 | Daily prices from 2006; dividends and splits from 1986 | From 2006 (the series starts 1980-01-02) |
| History | Filings from 2009; periods back to 2006–2007 | From listing; `^SP500TR` from 1988 | From 1980-01-02 |
| Point-in-time | Yes: every value carries its filing date and accession number | No: adjusted as of the day fetched | Yes: rates are not revised |
| Adjustments | None: values as reported | Prices and dividends split-adjusted; `adj_close` also dividend-adjusted | None |
| Gaps | No prices; tags differ between companies and over time | Delisted companies missing (survivorship bias); unofficial endpoint | US holidays have no rate; published weekly, about a week behind |
| Access | Free; a User-Agent with name and e-mail; at most 10 requests per second | Free; unofficial; kept to 1 request per second | Free; optional API key, otherwise the keyless CSV download |

Every source is fetched through `skatkis.io.api.ApiClient` and stored once per as-of
date as an immutable raw snapshot under `data/raw/<source>/<as_of>/`, in the vendor's
own format with a manifest of content hashes. Parsed tables are written as Parquet under
`data/interim/<source>/<as_of>/`. Request settings are in `config/market_data.toml`. A result is only reproducible together with the as-of
date of each source it used.

### SEC EDGAR: what was reported, and when

`EdgarCompanyFacts` fetches a company's `companyfacts` document: every value the
company has tagged in XBRL in any filing (10-K, 10-Q, their amendments, and some
others). `parse_companyfacts` keeps the tags listed in `tag_map.TAG_MAP` and returns one
row per reported value.

- **No market prices.** EDGAR holds what companies file. The only market figure is
  `dei:EntityPublicFloat`, the market value of shares held by non-affiliates on one day
  a year (the end of the second fiscal quarter), which is too coarse for pricing.
- **One row per value per filing.** The same period is reported again in later filings
  (as a comparative figure, or restated). Each repeat is a further row with its own
  `filed` date and `accession`; none is removed. The value first reported for a period
  is the one with the earliest `filed` date.
- **`filed` is the point-in-time key.** A rebalance on date $t$ may only use rows with
  $\text{filed} \le t$. Typical lags after period end: 40–45 days for a 10-Q, 60–90 days
  for a 10-K.
- **`fiscal_year` and `fiscal_period` belong to the filing, not to the value.** A 10-K
  for fiscal 2023 reports 2022 and 2021 as comparatives, all with `fiscal_year` 2023.
  The period of a value is given by `period_start` and `period_end`.
- **Flows and stocks.** Income and cash-flow values (flows) have a `period_start`;
  balance-sheet values (stocks) are instants and have none. A 10-Q reports the quarter
  and the year to date (six or nine months); there is no separate fourth quarter, so it
  follows from the annual and nine-month values,
  $$Q_4 = V_{\text{FY}} - V_{\text{9M}},$$
  where $V_{\text{FY}}$ is the fiscal-year value and $V_{\text{9M}}$ the nine-month
  year-to-date value of the same fiscal year.
- **`frame` is not point-in-time.** SEC's `frame` marks the one value it deems current
  for a calendar period, which is the latest filed, often a restatement.
- **Per-share figures are as reported.** EPS and dividends per share are not adjusted
  for later splits: Coca-Cola's EPS before its 2012 split stays on the pre-split basis.
- **Tags vary.** The same concept appears under different us-gaap tags between
  companies and over time; `TAG_MAP` lists them per field in priority order, and
  `tag_priority` and `tag` show which one a value came from. A lower-priority tag can be
  narrower than its field (`Depreciation` for `depreciation_amortization`). Not every
  company reports total liabilities; `liabilities_and_equity` allows them to be derived.
- **Units.** Monetary fields are in USD, per-share fields in USD per share, share counts
  in shares. A mapped tag reported only in another unit (a foreign-currency filer) stops
  the parse with an error naming the company and tag.
- **History.** XBRL filing began in 2009, so with comparative figures values reach back
  to periods ending in 2006–2007, and nothing earlier. Rules with long look-back windows
  (Graham's 10, 13 or 20 years, which the value tool shortens to 3 to 6 years) can only be
  evaluated from later rebalance dates.

### Yahoo Finance: what the shares traded at and paid out

`YahooChart` fetches a symbol's history from Yahoo's chart endpoint (the endpoint the
`yfinance` library uses); `parse_chart` returns three tables: prices, dividends and
splits. Daily bars from 2006 give the prices. Monthly bars from 1986 give the dividends
and splits (events keep their own dates), which keeps the request small.

- **Adjusted as of the fetch date.** `close` and dividend amounts are adjusted for every
  split up to the day the data was fetched; `adj_close` is adjusted for splits and
  dividends, so it is a total-return series. Coca-Cola's close around its 2:1 split on
  2012-08-13 shows about 39.4 on both sides, although it traded at about 78 before.
- **Returns from `adj_close`.** The return over a holding period, dividends reinvested,
  is the ratio of `adj_close` at its end and start.
- **Price ratios need the traded price.** Comparing a price with an EDGAR per-share
  figure (P/E, P/B, the Graham number) needs the price on the same basis as the filing:
  the traded price, recovered from the splits table as
  $$P^{\text{traded}}_t = P^{\text{close}}_t \times \prod_{s \in S_t} \frac{n_s}{d_s},$$
  where $S_t$ is the set of splits after day $t$ up to the fetch date, and split $s$
  gives $n_s$ new shares for $d_s$ old (`numerator`, `denominator`). Alternatively,
  compare company totals with market capitalisation.
- **Dividend history.** Dividends are requested from 1986, twenty years before the
  analysis period and longer than EDGAR reaches, so the 20-year dividend record can be
  evaluated from 2006. Only whether a dividend was paid in a
  year matters there, not its split-adjusted amount.
- **The benchmark.** `^SP500TR`, the S&P 500 total-return index, from 1988.
- **Survivorship bias.** Companies that were delisted (taken over, bankrupt) are not
  available, so a backtest over historical members sees only the survivors. Symbols can
  also be reused by another company later.
- **Unofficial.** The endpoint has no published terms or stability; requests are kept
  slow and every response is stored, so a pull is not repeated.

### FRED: what a dollar was worth in rand

`FredSeries` fetches a series from FRED, the Federal Reserve Bank of St. Louis's
database; `parse_fred` returns one row per day.

- **`DEXSFUS`** is the number of South African rand per US dollar, the Federal Reserve's
  H.10 noon buying rate in New York, daily from 1980-01-02; requested from 2006.
- **Not revised**, so the series as fetched is the series as it was known.
- **Missing days.** US holidays keep their row with a missing value.
- **Published weekly**, so the latest rates lag by about a week.
- **Access.** With `FRED_API_KEY` set, the official API (JSON); without it, the CSV
  download behind FRED's charts. Both give the same table.
- The tool fetches and stores the rate; it does not convert amounts between currencies
  yet.

### How the sources join

- **Company identity.** EDGAR identifies a company by CIK, Yahoo by ticker. Tickers
  change (a rename) and are reused, so the link between them belongs to a date: it
  comes from the historical S&P 500 membership, which is not built yet.
- **Dates.** EDGAR rows are dated by filing date and period end, Yahoo rows by trading
  day on the exchange, FRED rows by US business day. Each needs aligning to the
  rebalance date on its own terms.
- **Currency.** EDGAR values and Yahoo prices of S&P 500 members are in USD (the
  `currency` column of the price tables says so); `DEXSFUS` converts USD to ZAR.

## Updating the data

One terminal command brings the stored data up to a date; run it from the repository
root:

```
export SEC_USER_AGENT="Your Name your@email"   # required for EDGAR
export FRED_API_KEY=...                       # optional
.venv/bin/python -m Toolbox.market_data update --as-of $(date +%F) \
    --cik 320193 789019 21344 --ticker AAPL MSFT KO
```

- `--as-of` is always given, so a run never depends on the clock and can be repeated.
- `--source edgar prices fx` limits the run to some sources (default: all three).
- **EDGAR is incremental.** Each company's filing index (`submissions`) is checked
  first; its `companyfacts` are fetched again only if it has filed a 10-K or 10-Q on or
  after the date of its latest stored snapshot. Otherwise that snapshot is reused, and
  the `snapshot_as_of` column of the `facts` table says which one each row came from.
- Prices, dividends, splits and the exchange rate are small and fetched in full for
  each as-of date.
- Tables are written to `data/interim/<source>/<as_of>/` and the summary printed lists,
  per source, what was fetched, what was reused, what failed and the rows written; the
  reasons of the first ten failures follow.
- **Every table passes its gate before it is written** (below). A company's facts and a
  symbol's prices, dividends and splits are checked on their own first: one that breaks
  its schema, or has a column too many or too few, is left out and listed as failed with
  the reason, like a fetch or parse failure, and the rest of the update goes on. The
  combined tables of a source are then all checked before any is written, so a failure
  there (a key repeated across companies or symbols) leaves the folder as it was.
- Until the historical S&P 500 membership is built, the companies (`--cik`) and symbols
  (`--ticker`) are given on the command line; `^SP500TR` is always added.
- The command can be scheduled (macOS `launchd` or `cron`), for example weekly or after
  each earnings season.

### Stored tables and their gate

Each stored table has a schema in the source module that produces it, built from that
module's column-to-dtype map, so a column is declared once:

| Table | Folder under `data/interim/` | Schema (module) | Key |
|---|---|---|---|
| `facts` | `edgar_companyfacts/<as_of>/` | `FACTS_TABLE_SCHEMA` (`sources/edgar.py`) | `cik`, `accession`, `field`, `tag`, `unit`, `period_start`, `period_end` |
| `prices` | `yahoo/<as_of>/` | `PRICE_SCHEMA` (`sources/prices.py`) | `symbol`, `date` |
| `dividends` | `yahoo/<as_of>/` | `DIVIDEND_SCHEMA` (`sources/prices.py`) | `symbol`, `ex_date` |
| `splits` | `yahoo/<as_of>/` | `SPLIT_SCHEMA` (`sources/prices.py`) | `symbol`, `date` |
| `listings` | `yahoo/<as_of>/` | `LISTING_SCHEMA` (`sources/prices.py`) | `symbol` |
| `constituents` | `constituents/<as_of>/<index>/` | `CONSTITUENT_SCHEMA` (`sources/constituents.py`) | `symbol` |
| `changes` | `constituents/<as_of>/<index>/` | `CHANGE_SCHEMA` (`sources/constituents.py`) | none: one date may carry several changes |
| `observations` | `fred/<as_of>/` | `OBSERVATION_SCHEMA` (`sources/fred.py`) | `series_id`, `date` |

The facts key includes `period_start`, which is missing for an instant; two instants
that agree on every other key column count as duplicates.

The gate, `validation.check_table`, passes a table when its columns are exactly those of
its schema (none undeclared, none missing) and every constraint holds; dtypes are not
checked. It runs where `update.py` writes a table (the update lists its tables in
`update.TABLE_SCHEMAS`) and where a tool reads one (each tool lists the stored tables it
reads in its own `schema.py`, so it never imports the update to read). The main
constraints:

- **Prices** are positive where present (a day without a trade has missing prices, never
  0), volume is non-negative, and prices and dividends must be in USD
  (`prices.PRICE_CURRENCY`), since every later stage reads them as USD. Dividend amounts
  and both parts of a split ratio are positive.
- **Members** each have a GICS sector and sub-industry; the sectors carry no allowed set.
- **Facts** may hold only the fields, taxonomies, tags and units of `TAG_MAP`, the ones
  the parser reads. The read gate checks them too, so a facts table parsed under an
  earlier `TAG_MAP` is refused until it is parsed again; `update` parses each company's
  snapshot again on every run, the reused ones included. `filed` may precede `period_end` (a dividend declared ahead, a
  share count on a cover page), so that is not a constraint.

## Checking the data and the report

```
.venv/bin/python -m Toolbox.market_data check --as-of 2026-10-31
```

reads the tables written for that as-of date, prints numeric checks and writes the plots
and the report under `results/market_analysis/<as_of>/`. The main text is a concise view
of the last five years (`[analysis] recent_years` in `config/market_data.toml`):

1. **Introduction**: the GICS sectors (description, companies, fund); company names are
   in the ticker appendix.
2. **Per analysis** (fundamentals, total return, relative return, P/E, dividend yield):
   the sector summary (revenue and net income side by side in USD trillions; total
   return over 5 years, 10 years and the full history in three rows), a 3 x 3 grid with
   every sector's five best (solid) and five worst (dashed) companies, and an overview of
   the two best and the two worst sectors with their five best or worst companies.
3. **P/E and value**: the five lowest-P/E companies beside the five with the best total
   return (and the highest P/E beside the worst return), each plot showing both P/E and
   price growth per company, and the companies found in both lists.
4. **Appendix**: tickers and names by sector; every sector's ten best and ten worst
   companies over the full history per analysis; the P/E lead-lag; the data checks.

"Best" follows the analysis (`rankings.py`); main-text rankings use the last five years
and only companies with prices for the whole window (`rankings.window`).

| Analysis | Company score | Sector score | Best |
|---|---|---|---|
| Fundamentals | annualised revenue growth (at least 3 years) | median of its companies | highest |
| Total return | annualised total return | its fund's | highest |
| Relative return | annualised return relative to the sector fund | its fund's against the S&P 500 | highest |
| P/E | median P/E | median of its companies | lowest |
| Dividend yield | mean trailing yield | median of its companies | highest |

Each panel is a separate image; the LaTeX report joins them into grids and side-by-side
figures with lettered sub-captions. A line plot holds at most 30 lines.

The fiscal year of the as-of date is left out of the fundamentals totals, as it is not
over. The P/E, lead-lag and dividend-yield tables are stored under
`data/interim/metrics/<as_of>/`. `results/` is tracked in git, so new and changed plots
show in the changes view; the raw and parsed data stay in the git-ignored `data/`.

The command then writes `report.tex` next to the plot folders: a LaTeX article with a
title, an abstract, a table of contents, the sections above with numbered captions,
clickable cross-references (`hyperref`) and the appendix. Its text comes from `config/report_market_analysis.toml`.
When a LaTeX engine is installed (`tectonic`, `latexmk` or `pdflatex`; for example
`brew install tectonic`), the command compiles it to `report.pdf`.

The plots are named functions in `market_analysis.py` (`fundamentals_sector`,
`sector_relative`, `dividend_yield_sector`, ...), one per thing shown, with its titles and
units; the modelling tools call them too. They are built on the generic layouts of
`skatkis.analysis`, which know no source or metric; `skatkis.report` writes the LaTeX.

The lead-lag profile correlates the monthly log change of the P/E at month $t$ with the
monthly log change of the price at month $t + k$, for $k$ from $-12$ to $12$; a positive
$k$ means the P/E changes first. P/E is price divided by EPS, so the two move together at
$k = 0$ by construction; the other lags carry the information. With $n$ months, a
correlation within about $\pm 2 / \sqrt{n}$ is indistinguishable from chance.

## Universe and benchmarks

- **Members** come from Wikipedia's "List of S&P 500 companies" (symbol, GICS sector and
  sub-industry, date added, CIK); index changes from "Historical components of the S&P
  500" (complete from about 2007). Both are fetched through the MediaWiki API and stored
  like every other source (`sources/constituents.py`).
- **GICS map** (`gics.gics_map`): one row per company with its price symbol, CIK, GICS
  sector and sector fund, like the tag map for XBRL tags. Analysis merges it onto a
  table and groups by `gics_sector`; each group is normalised the same way against its
  own `sector_fund`. The universe is the current members outside the excluded sectors
  (Financials, Real Estate; `[universe]` in `config/market_data.toml`). `update --universe sp500` pulls
  their filings and prices. Only current members are included, so companies that left
  the index are missing (survivorship bias); the membership at past dates follows.
- **Benchmarks** (`[benchmarks]`): the market is `^SP500TR`; each GICS sector is
  compared with its SPDR sector fund (`XLK` for Information Technology, `XLP` for
  Consumer Staples, ...). The funds track the S&P 500 sector indices and their adjusted
  close includes dividends, so companies, sectors and market are all compared on total
  return; the sector indices on Yahoo (`^SP500-45`, ...) are price-only.
- With more than 10 companies, the checks draw sector plots instead of per-company plots.

## Cleaning and metrics

- **One tag per value** (`clean.select_tags`). A field (`TAG_MAP`) can be reported under
  several XBRL tags, even in one filing. Per company, the tag used most recently ranks
  first, so each field follows the company's current tag; ties go to the lower
  `tag_priority`.
- **First-reported annual values** (`clean.annual_first_reported`): per company and
  fiscal year, the value as first filed in a 10-K; flows count as annual when they span
  350 to 380 days.
- **P/E** (`metrics.price_earnings`): the close divided by the latest first-reported
  annual diluted EPS filed before the day. The EPS is put on the price's split basis
  first: with $F(d)$ the product of the split ratios after day $d$,
  $$\text{P/E}_t = \frac{P^{\text{close}}_t}{\text{EPS} / F(d_{\text{filed}})},$$
  where $d_{\text{filed}}$ is the EPS's filing date. The P/E is missing where the EPS is
  zero or negative. It uses annual EPS, so it steps once a year; a P/E on trailing
  twelve-month EPS follows once quarterly values are cleaned.
- **Dividend yield** (`metrics.dividend_yield`): dividends with an ex-date in the past
  365 days divided by the close,
  $$y_t = \frac{\sum D}{P^{\text{close}}_t},$$
  both split-adjusted to the fetch date, so the ratio is consistent; 0 when no dividend
  fell in the window. Amounts from EDGAR (revenue, net income) are in USD; plots show
  them in USD millions.
