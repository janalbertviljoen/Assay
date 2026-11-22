---
paths:
  - "Toolbox/*/schema.py"
  - "Toolbox/*/contracts.py"
  - "Toolbox/skatkis/pipelines/**"
  - "Toolbox/*/sources/**/*.py"
  - "Toolbox/market_data/update.py"
---

# Schema and layer contracts

- `schema.py` is the single source of truth for a pipeline's canonical columns: name,
  dtype, unit, constraint flags (`required`, `positive`, `non_negative`, `unique_key`),
  owner and derivation. No other module redefines a column. No calculations, IO or
  validation execution here.
- A stored table's schema lives in the source module whose data it holds, built from
  that module's dtype map with `from_dtypes` (`PRICE_SCHEMA`, `LISTING_SCHEMA` in
  `market_data/sources/prices.py`, `FACTS_TABLE_SCHEMA` in `sources/edgar.py`).
  `market_data/update.py` lists the tables it writes in `TABLE_SCHEMAS`; a tool lists
  the stored tables it reads, with those schemas, in its own `schema.py`
  (`value_investing.schema.INPUT_TABLES`) and never imports `market_data.update` to
  read (user, 2026-11-08; S_202611_005).
- A constraint is declared hard only when it holds by construction of its producer or
  by definition of the quantity; one that rests on vendor data that can be wrong in a
  single filing is a soft expectation (`expect_*`), reported and never raised.
- Layer input schemas reference the upstream entry directly to keep lineage.
- `contracts.py` holds the pipeline contracts: name, inputs, output schema, grain
  (ticker × as-of date), immutable inputs, description. Use only the fields of the
  shared contract type in `skatkis.pipelines`; a generic need is added there, with
  tests.
- Register contracts in DAG dependency order, consistent with `pipeline.py`.
- Renaming a canonical column: `developer.md`, "Coding conventions", and `writing.md`,
  "Renames and the trail".
