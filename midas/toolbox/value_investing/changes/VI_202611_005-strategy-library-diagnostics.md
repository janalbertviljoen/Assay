# VI_202611_005: Strategy library and two market diagnostics

| Field | Value |
|---|---|
| Status | in progress |
| Priority | medium |
| Kind | tooling |
| Depends on | none |
| Branch | `feature/value-investing/analysis-2026-11-22` |
| Raised | 2026-11-22 |

## Description

The user wanted a basis for analysing other strategies: a library of trading-strategy
texts, papers and long-history data, and two tests of when to step out of the market
(valuation spread, trend following). Exploratory work in `Toolbox/SandBox/`, outside the
standard; the results are diagnostics, not adopted methodology.

## Agreed approach

- **Library:** legally free texts, papers and data only, in a dated, git-ignored snapshot
  (`data/raw/library/2026-11-22/`, manifest with licence and SHA-256); text extracted to
  `data/interim/library/`. Copyrighted books are bought, not downloaded. Fetch tools in
  `Toolbox/SandBox/strategy_library/`.
- **Readers:** a `library` dependency group (`xlrd`, `pypdf`) for the legacy `.xls` data
  and the PDF texts.
- **Diagnostics,** each with its design fixed before the run (`quant.md`):
  `Toolbox/SandBox/valuation_spread/` and `Toolbox/SandBox/trend_following/`.
- **Private data stays private:** the list of the owner's funds and their fact sheets live
  in `~/Documents/Personal/Finances/fund_sheets/`, never in this repository; public index
  factsheets (MSCI) in `data/raw/index_sheets/`.

## Decisions

- 2026-11-22 (user): private use relaxes licence restrictions on what the library may
  hold, but not to unauthorised copies of copyrighted books.
- 2026-11-22 (user): new dependencies `xlrd` and `pypdf` in a `library` group.
- 2026-11-22 (user): the work is reviewed as uncommitted changes before any commit.
- 2026-11-22 (user): commit, push, and the Warden on the whole branch before closing.

## Notes

- 2026-11-22: results recorded in `midas/toolbox/value_investing/notes.md`: "A strategy
  library", "Valuation spread as a sell-everything signal", "Trend following as the sell
  rule", "Market valuations by region".
- 2026-11-22: corrected before recording: a wrong ticker in the owner's private fund list
  (a different fund's fact sheet was fetched; found because its top holdings did not match
  the fund's index); a missing T-bill value read as "cash" in the latest trend signal.
- Still to fetch: six Gutenberg books and one AMS paper
  (`Toolbox/SandBox/strategy_library/still_to_fetch.tsv`); the sandbox proxy refuses those
  hosts.

## Done when

- The Warden's report is in this file and its findings are fixed or answered.
- The branch is merged; the outcome minutes replace the approach, decisions and notes.

## Inspections

| Date | Commits | Findings | Open |
|---|---|---|---|

## Warden report
