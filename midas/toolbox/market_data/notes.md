# market_data notes

## Planning (preliminary)

### Snapshot identity ignores request settings (2026-10-31, open)

A snapshot is keyed by source name, query and as-of date. A changed request setting
(the start date in `config/market_data.toml`) with the same as-of date silently reuses
the stored snapshot. Today the rule is to take a new as-of date; recording the request
settings in the manifest and refusing a mismatch would make it safe.

### Other exchanges for out-of-sample tests (2026-10-31, → MD_202610_004)

Surveyed to test the value rules' reliability beyond the S&P 500; from knowledge, not
yet verified at the sources. Prices are no constraint (Yahoo covers most exchanges);
first-reported, dated fundamentals are, since restated vendor data may not be used for
scoring.

| Market | Free dated fundamentals | History | Assessment |
|---|---|---|---|
| US, Dow Jones 30 | EDGAR | about 2009 on | All members are S&P 500 members: a benchmark only |
| US, S&P 400 and 600 | EDGAR | about 2009 on | Same pipeline, about 1,000 new companies: chosen |
| Japan (TOPIX, Nikkei 225) | EDINET XBRL, free API key | about 10 years | Best free non-US source; new taxonomies, JPY |
| South Korea (KOSPI 200) | OpenDART, free API key | about 2015 on | Workable, effort like Japan |
| UK and EU (FTSE, STOXX) | ESEF iXBRL (FCA NSM, filings.xbrl.org) | FY2020 on | Too short for a quarterly backtest today |
| JSE (Top 40) | none, PDFs only | none | Returns-only comparison (MD_202610_003) or a paid vendor |
| Canada, Australia, India | none usable | none | Not pursued |

Dual-listed JSE and LSE companies that file 20-F reports on EDGAR (Sasol, Gold Fields,
AngloGold, BP, Shell, HSBC, AstraZeneca and others) carry IFRS XBRL from about 2017:
too few to rank an index, enough to spot-check rules. Paid point-in-time vendors with
global coverage (Compustat Global, LSEG Worldscope, FactSet) reopen the data budget of
spec §9.1. The user chose a broader US universe (2026-10-31); Japan and ESEF stay
candidates for later.

### Financial Modeling Prep (FMP) MCP server as a candidate source (2026-11-04, open, parked)

The user has an FMP API key and its MCP endpoint (`https://financialmodelingprep.com/mcp`,
key passed as the `apikey` query parameter). Parked until there are more tokens (user,
2026-11-04); not connected, nothing fetched. The key is not recorded here or anywhere in
the repository.

- **Standing decision it touches:** free sources only (MD_202610_001, decided 2026-10-31).
  FMP is a vendor; its tier and limits are unchecked.
- **Gaps it might fill:** companies that left the index (survivorship), predecessor CIKs,
  quarterly figures for the floating P/E idea (value_investing notes, "Infer rules between
  filings"), and the 400 and 600 membership history (MD_202611_001).
- **To check before use:** whether values are point-in-time and first-reported or restated
  (`quant.md`); the free tier's history and call limits; the terms on storing the data.
- **If connected:** the key comes from the environment (`FMP_API_KEY`), registered at local
  scope or with variable expansion, never written into the checked-in `.mcp.json`; raw data
  goes only into the git-ignored `data/`. The key was pasted into a chat on 2026-11-04, so
  rotate it.

## Data issues

### Yahoo prices and dividends are split-adjusted as of the fetch date (2026-10-31, open → MD_202610_002)

Yahoo's `close` and dividend amounts are adjusted for every split up to the fetch date;
`adj_close` is also adjusted for dividends. Checked on Coca-Cola's 2:1 split of
2012-08-13: `close` is about 39.4 on both sides (about 78 actually traded before), and
2012 dividends show 0.255 (0.51 paid per pre-split share). EDGAR per-share figures are
as reported, so price ratios (P/E, P/B, Graham number) need the split adjustment undone
first, from the splits table, or must be computed from market capitalisation and
company totals instead.

### Companies switch tags over time: choose the tag per period (2026-10-31, resolved)

Found in the first data checks. Choosing one tag per company for all years loses most
of the history: Apple reported revenue as `SalesRevenueNet`, then `Revenues`, then the
ASC 606 tag. The best available tag (lowest `tag_priority`) must be chosen per company,
field and period; with that, revenue is complete for all three companies from 2007.
Resolved 2026-10-31 (user): the company's most recently used tag is canonical
(`market_data.clean.select_tags`).

### Per-share comparatives are restated for splits (2026-10-31, open → MD_202610_002)

Apple's diluted EPS for 2011–2013 is 27, 44 and 40 as first reported, before the 7:1
split of 2014; later 10-Ks repeat those years split-adjusted (about 6.3 and 5.6), and
the 4:1 split of 2020 does the same for 2018–2019 (11.9 and 2.97). So the first-reported
value of a per-share figure is on its own pre-split basis, while comparatives move to
the later basis. Rules comparing per-share values across years (G3, G5, E5) need them on
one basis, from the Yahoo splits table, applied point-in-time (only splits before the
rebalance date).

### Share count reported on two dates per 10-K (2026-10-31, open → MD_202610_002)

`shares_outstanding` comes from the cover page (`dei:EntityCommonStockSharesOutstanding`,
dated a few days before filing) and from the balance sheet
(`us-gaap:CommonStockSharesOutstanding`, dated at the period end), so a 10-K can give two
share counts with different dates. The point-in-time stage must pick one convention
(the cover-page count is the latest known at filing).

### One field in another unit drops the whole company (2026-10-31, open)

The full pull lost two companies (CIK 32604 and 864749) because one mapped field,
`dividends_per_share`, is reported in `pure` or `EUR`; the parser stops at a unit
mismatch, so all their fields are lost. Option: drop only the field's values in the
wrong unit and report it, keeping the company. This changes the "fail fast on unit
mismatch" rule in `.claude/rules/sources.md`, so it is the user's decision.

### Large daily moves (2026-10-31, open)

931 daily total-return moves above 20% across 409 symbols since 2006; plausible (earnings
and 2008/2020), but not yet inspected for data errors such as unadjusted splits.

