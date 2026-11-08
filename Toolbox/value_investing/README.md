# value_investing

The value-investing tool: S&P 500 fundamentals extracted point-in-time, Graham /
Buffett / Munger rules, a quarterly top 10 and bottom 10, and strategies backtested
against the S&P 500.

Until the code is final, the methodology is specified in
[docs/value_investing_bot_spec.md](../../docs/value_investing_bot_spec.md); this README
replaces it once the tool is built.

The tool reads its data (sources, cleaned tables and shared metrics such as the P/E) from
the shared package [market_data](../market_data/README.md); it owns the rule thresholds,
gates, ranking and strategies.

## Gates

Every table is checked at the boundary where it enters or leaves the tool.

- **Stored tables, on read.** The command line (`python -m Toolbox.value_investing`)
  checks each stored market table as it reads it (`facts`, `prices`, `dividends`,
  `splits`, `listings`, `constituents`, `changes`) with the stored-table gate of
  `market_data` (`market_data.validation.check_table`; see "Stored tables and their
  gate" in the [market_data README](../market_data/README.md)). The tables it reads and
  their schemas are listed in `schema.INPUT_TABLES`; the schemas are owned by the
  `market_data` source modules, so the tool never imports the update to read. A facts
  table parsed under an earlier `TAG_MAP` is refused until `market_data update` parses
  it again. Callers that pass their own tables to `pipeline.buyability` (notebooks, the
  MCP tools) are not checked on input, and the stored buyability tables, this tool's
  own output, are not checked when `evaluate` and `report` read them.
- **The buyability table, on output.** `pipeline.buyability` runs
  `validation.check_buyability` before it returns, so every caller is gated. The table
  must have exactly the columns `schema.buyability_schema` declares (none undeclared,
  none missing, even one that may hold missing values), one row per (`symbol`, `date`),
  and meet every constraint. A constraint is hard only when it holds by construction of
  the layer that produces it (a flag is 0, 1 or missing; points are whole grades from 0
  to `buckets` − 1; a learned score is non-negative) or rests on a stored table that is
  itself gated (a positive `close`, a `gics_sector` for every company). The [0, 1] and
  non-negative bounds allow an absolute rounding slack of $10^{-12}$; a positive bound
  has none.
- **Soft expectations.** `market_cap` and `pb` rest on EDGAR's first-reported share
  counts, which can be wrong in a single filing, so a negative value is a soft
  expectation: it is listed in `Buyability.report`, never raised, and one bad filing
  cannot stop a run. The `buyability` command prints each view's report.
- **Dtypes** are not checked by these gates.

## Default rules

Ten rules score by default: G6, G2a, G7, G2b, E2, NN, E1, G5, B1 and E4 (eight concepts,
because G2a and E1 and G2b and E2 rank on the same values). G3, G4, E3, E5, E6 and NI1
are off. To switch one on, remove the leading `#` of its table in
[config/rules.toml](../../config/rules.toml) (for example `[rules.G3]` and its `years`);
to switch one off, put the `#` back. The windows and thresholds are explained in
[docs/value_investing_bot_spec.md](../../docs/value_investing_bot_spec.md), section 2.
