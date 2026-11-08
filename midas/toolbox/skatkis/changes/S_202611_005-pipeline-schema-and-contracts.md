# S_202611_005: Pipeline schema, contracts and validation, and value_investing on them

| Field | Value |
|---|---|
| Status | in progress |
| Priority | high |
| Kind | refactor |
| Depends on | none; S_202611_003 takes the node registry |
| Branch | `feature/skatkis/s-202611-005-pipeline-schema` |
| Raised | 2026-11-07 |

## Description

The columns of the pipeline exist only in code: `inputs.RuleInputs` carries
`(field, lag)` columns, the layers read them by position in a dataclass, and nothing
declares a column's dtype, constraints, owner or grain. Validation is ad hoc
(`market_data/checks.py`, scattered asserts). The user added a template of an
enterprise-grade pipeline framework (`midas/skatkis.zip`, from another repository). Its
schema, source and contract modules are what we lack. This change brings them into
`skatkis` and binds `market_data` and `value_investing` to them, with no change to any
result.

## Agreed approach

1. **Take from the template** (`pipelines/`): the schema vocabulary and `PipelineSchema`,
   `SourceSchema`, `Grain`, ownership and `bind` (`schema.py`); `LayerContract` and
   `safe_merge` (`contracts.py`); `LookupModel` and `ColumnMap` (`sources.py`);
   schema-driven validation on Pandera and the `assert_*` functions (`validation.py`);
   `Notice` and `PipelineReport` (`report.py`, `report_checks.py`); the registry as the
   only shared state; `from_paths` and `from_records`.
2. **Drop from the template**: `branding.py`, `KPMG_branding`, `io/word.py`,
   `io/office_math.py`, `io/images.py`, `io/excel.py`, `pipelines/output.py`,
   `pipelines/preface.py`, `accreditation/`, `fault_injection/`, `saspy_wrapper/`,
   `sas_code/`, `financial_logic/economics.py`, `financial_logic/rating_agency.py`,
   `numerics/curve_interpolation.py`, `pipelines/lookup_extraction.py` and `steward/`
   (Midas's index replaces it). `pipelines/ui.py` is deferred: its `override_column` is
   the scenario mechanism of S_202611_003.
3. **Execution stays the spec §6 node graph** (`graphlib`, edges inferred from `inputs`),
   not the template's linear `DAGLayer` list; this is S_202611_003's. A template layer's
   `(df, registry) -> df` body becomes a node body, and its `LayerContract` the node's
   schema.
4. **Pandera is adopted** (user, 2026-11-07), installed and pinned as `core`.
5. **First slice, phases 1 and 2** (user, 2026-11-07):
   1. `skatkis.pipelines` gains `schema`, `contracts`, `validation` and `report`; the
      `value_investing` schema is declared and asserted on the existing `buyability`
      output.
   2. Amended 2026-11-08 (Decisions, "phase 2 amended"): a schema per stored
      `market_data` table (`facts`, `prices`, `dividends`, `splits`, `listings`,
      `constituents`, `changes`, `observations`) in its source module, gated where
      `update.py` writes and where `value_investing` reads. `SourceSchema` and `bind`
      wait for phase 3; `universe` is built in memory by `index_universe` and has no
      stored schema.
6. **Later phases, not in this slice**: the nodes (S_202611_003), then replacing
   `RuleInputs` with frames on canonical column names, rule by rule.
7. **A refactor**: `regression_check` returns `unchanged`, and the buyability tables and
   report summaries of the S&P 500, 400 and 600 are identical before and after.

## Decisions

- 2026-11-07 (user): the drops of step 2 are agreed.
- 2026-11-07 (user): Pandera is installed, good practice; 0.35.0, with its
  dependencies `typeguard` 4.6.0 and `typing-inspect` 0.9.0.
- 2026-11-07 (user): this is a refactor, on its own branch.
- 2026-11-07 (user): the first slice is phases 1 and 2.
- 2026-11-08 (user): the [0, 1] and non-negative bounds allow an absolute rounding
  slack, `BOUND_TOLERANCE = 1e-12`, defined once in `skatkis.pipelines.validation`
  and used by the hard checks and the soft expectations alike; the positive bound has
  none. Raised by the first gated run: `score_weighted_share` is
  $1 + 2.2 \times 10^{-16}$ on nine rows of the S&P 400 and 600 (companies with full
  points on every evaluable rule). Rejected: clipping in `value_investing.scoring`
  (moves the baseline, a methodology change) and dropping the flag (loses the check).
- 2026-11-08 (user, on the Inspector's finding 1): constraints that rest on the stored
  tables, not on their layer, are split by source until phase 2 moves them to the
  source schemas. Hard: `close` positive and `gics_sector` present (prices and the
  universe are clean; a gap is a real defect), and `pe_average` positive (given a
  positive `close`). Soft (`expect_non_negative`, reported, never raised):
  `market_cap` and `pb`, which rest on EDGAR's first-reported share counts, so one bad
  filing cannot stop a run. Rejected: all hard (one bad share count stops a quarterly
  run) and all soft (a missing price or sector would pass unseen).
- 2026-11-08 (user): **phase 2 amended** (step 5.2 of the agreed approach). The
  template's `bind` assumes value columns in one shared namespace, joined by key; the
  stored tables do not fit it: names repeat across stages (`prices.close` is the daily
  close, the buyability `close` the close on a rebalance date, so `PipelineSchema`
  rejects it as both input and output), the facts are long-form (a fundamental is a
  value of `field`, not a column), and `rule_inputs` aligns filings and prices point in
  time rather than joining by key (the facts are keyed on `cik`). Phase 2 instead
  declares a schema per stored table in `market_data` (key, dtypes, constraints by
  construction of its parser) with a gate where `update.py` writes a table and where the
  tables are loaded for `value_investing`. `SourceSchema` and `bind` are not used yet;
  revisited in phase 3, when the nodes have real layer contracts. Rejected: the full
  template binding (renamed columns, facts pivoted wide; touches names used by notebooks
  and reports and risks the no-change guarantee) and stopping after phase 1.
- 2026-11-08 (user, on the Warden's note 7): the read-side table schemas live in
  `value_investing/schema.py` (`INPUT_TABLES`), so the tool never imports
  `market_data.update` to read. The schemas stay owned by the `market_data` source
  modules; `listings` (`LISTING_SCHEMA`) moved to `sources/prices.py` and the stored
  facts (`FACTS_TABLE_SCHEMA`, with `snapshot_as_of`) to `sources/edgar.py`, so neither
  the writes nor the reads define a column twice. Rejected: moving every table schema
  into `value_investing` (then `market_data` could not gate its writes, since it may
  not import a tool).
- 2026-11-08 (user, on the Warden's finding 1): `midas/skatkis.zip`, the template,
  stays out of the repository: unstaged and git-ignored, kept on the user's disk only.
- 2026-11-08 (user, on the Warden's finding 5): the update's behaviour on bad data is a
  decided change, not part of the refactor's no-change guarantee, which covers
  results: a company's facts or a symbol's prices, dividends and splits that fail
  their schema, or have a column too many or too few, are left out and listed in
  `UpdateResult.failed` with the reason, and the rest of the update goes on; the
  combined tables are checked again and all of them before any is written, so a
  failure leaves the folder as it was. Rejected: failing the whole update on one bad
  table. To be stated in the pull request description.
- 2026-11-08 (user, on the Inspector's finding 3 of inspection 2): the facts read gate
  keeps the allowed fields, taxonomies, tags and units taken from `TAG_MAP`, so a facts
  table parsed under an earlier `TAG_MAP` is refused until parsed again (it no longer
  matches what the code maps; `update_edgar` parses each company's latest snapshot again on every run, a reused one included).
  Rejected: checking the allowed sets on write only.

## Open decisions (user)

- Whether the node registry (S_202611_003) is renamed or absorbed once phase 3 starts.
- Phase 3, from the Warden's notes: whether `market_data/checks.py`, `market_data/__main__.py` and
  callers passing their own `Tables` to `pipeline.buyability` are gated too (note 8);
  whether dtypes are validated, as spec §6.1 asks of a node's schema, which the gates do
  not do yet (note 10, a contradiction between spec and code, recorded here).
- How the `(field, lag)` annual history is named as columns (for example
  `eps_diluted_lag0`) or held as a long table; decided before phase 4.

## Notes

- 2026-11-07: branch created from `main`. The uncommitted S_202611_004 work was stashed
  (`git stash list`, "S_202611_004 beta access") and is popped back on its own branch.
  The two changes both add a row to this folder's `CHANGELOG.md` and edit
  `pyproject.toml`; expect a small merge conflict in each.
- 2026-11-07: `midas/skatkis.zip` is the template, untracked; unpacked copies are kept
  only in the scratchpad.
- 2026-11-08: **baseline recorded** at `main` (`ebe4700`), data as of 2026-10-31. The
  buyability result (table, learned weights, rank correlations) of the S&P 500, 400 and
  600, in both views (`on_date`, `current`): 18 tables, written to the scratchpad only
  (nothing under `results/` or `data/`). A second run gave identical content hashes, so
  the run is deterministic. The comparison script is `baseline.py` in the session
  scratchpad (`save` and `check`); it is not committed. The report summaries are not
  yet part of the baseline.
- 2026-11-08: starting state of the checks on `main`: Black, ruff and pyright clean;
  pytest 62 passed and **14 failed**, all in `tests/value_investing/test_report.py`
  (`test_tier_boundaries`, 13 cases, and `test_worst_table_rows_follow_the_input_order_with_tiers`):
  they call `_tier` with three arguments, the function takes two. Stale tests, not
  caused by this change; not fixed here (`AGENTS.md`, "Prohibited"), for the Tester.

- 2026-11-08: **`schema.py` and `contracts.py` ported** to `Toolbox/skatkis/pipelines/`
  (unstaged, with the dependency edits). From the template: the vocabulary, `Grain`,
  `PipelineSchema`, `SourceSchema`, `Finding`/`BindingError`, `Ownership`, `bind` and
  `LayerContract`/`safe_merge`. Removed: `default_exposure`, `default_annual`,
  `type_rate`, `type_exposure` (loan-specific) and the SOP and loan references in the
  docstrings. Added: the aliases `ColumnMeta` and `Schema` in `contracts.py`, replacing
  the template's bare `dict` (strict pyright reported 150 errors on the copy); typed
  defaults; imperative docstring summaries. Black, ruff and pyright are clean on
  the package. Smoke-tested on a toy schema in the scratchpad (not a repository test:
  the Tester writes the tests last). Next: `validation.py` and `utils.py` (Pandera),
  then `report.py`.
- 2026-11-08: **`validation.py` ported** (unstaged): `validate_from_schema` (public; the
  template's `_validate_from_schema`), `to_pandera_schema`, `SchemaValidationError` and
  the hard assertions (`assert_required_columns`, `assert_required_if`,
  `assert_no_nulls`, `assert_unique_key`, `assert_probability_bounds`,
  `assert_positive`, `assert_non_negative`, `assert_allowed_values`,
  `assert_constant_columns`). The flag accessors of the template's `utils.py` are
  private helpers here, so there is no `utils.py`. Left out until a need appears:
  `cast_and_fill` (it lower-cases every string column not tagged `identifier`, which
  would turn symbols and sector names to lower case; our cleaned tables are already
  typed Parquet), the soft filtering (`flag_from_schema`, `filter_valid_rows` and their
  masks, for client files), the mapping, writer, registry, override and solver checks.
  Pandera's untyped built-in checks and `failure_cases` are reached through typed
  helpers, without ignores. Smoke-tested in the scratchpad: seven kinds of violation
  reported together with sample keys, the input unchanged, a missing column named;
  0.01 s on the S&P 500 `current` table (25,980 rows). Dtypes are not checked by
  the validator, as in the template.
- 2026-11-08: **`report.py` ported** (unstaged): `Notice`, `PipelineReport` and
  `build_report`, and the soft-expectation scan (`soft_violations`,
  `expectation_notices`, `SOFT_EXPECTATIONS`). Changed from the template: no registry
  (it comes with the nodes in phase 3), so `build_report` runs checks over any state
  the caller passes and the scan works on one table and its schema; the scan is
  vectorised (the template looped per row with `.at`); `summary()` returns text and the
  caller prints. `report_checks.py` is not ported: it reads `LookupModel` column maps,
  which this slice does not use. Smoke-tested: the S&P 500 `current` table gives
  75,673 missing rule values on eight rules in 0.02 s. Next: the phase 1 milestone,
  the `value_investing` schema asserted on the buyability output.
- 2026-11-08: **phase 1 milestone** (unstaged). `value_investing/schema.py`:
  `pipeline_schema(rule_ids, *, buckets)` builds the `PipelineSchema` from the
  configured rules (inputs `symbol`, `date`, `gics_sector`; layers `rule_inputs`,
  `valuation`, `rules.<ID>`, `points`, `score`, `score_ic`), and `buyability_schema`
  the table's schema keyed on (`symbol`, `date`). Each constraint holds by construction
  of its layer, not only on the data seen (for example `pe_average` positive,
  `score_ic` non-negative, flags in {0, 1}, points in {0, …, buckets − 1}).
  `value_investing/validation.py`: `check_buyability`, the output gate: columns
  exactly the declared ones (none undeclared, none missing), then the schema checks.
  `pipeline.buyability` runs the gate before it returns (the design said `__main__`;
  in `pipeline.py` every caller is gated, including the MCP tools and notebooks).
  Two fixes found by testing the gate: a declared column that may hold missing values
  could be absent (Pandera's `required=False`), now required by the gate; a frame with
  repeated row labels failed inside Pandera, now checked on a renumbered copy.
  Results: the 18 baseline tables identical; the gate rejects an extra column, a
  flag of 0.5, a grade of 7, a duplicate key (with and without repeated labels), a
  missing column and a negative close. Black, ruff, pyright clean; pytest 62 passed,
  the same 14 stale failures.

- 2026-11-08: **inspection 1 fixes** (unstaged). Pandera floor `>=0.35` (the
  `pandera.pandas` module needs a recent release); `contracts.py` docstring cleared of
  the template's registry and `preface` references; `BOUND_TOLERANCE` moved to the
  schema vocabulary (`skatkis.pipelines.schema`), so `report.py` no longer imports the
  Pandera chain; the renumbered-copy naming documented; a comment at the gate call.
  Finding 1 as decided above: `market_cap` and `pb` soft; `Buyability` gains a
  `report` (the soft-expectation notices), printed by the `buyability` command;
  `value_investing/schema.py` says which constraints rest on the stored tables. Kept,
  for phase 2: the schema vocabulary not yet used (`required_if`, `computable_from`,
  `segment`, `result`, the defaults), `LayerContract`, `bind` and
  `segmentation_source="universe"`. For the Tester (from the Inspector): the caller's
  frame unchanged by `validate_from_schema` (values and dtypes); a real Pandera
  failure through `failure_cases`; the Pandera check names `_describe_failures`
  relies on (`column_in_dataframe`, `not_nullable`, `field_uniqueness`,
  `multiple_fields_uniqueness`). Results: the 18 tables identical, no soft notices on
  any index or view; Black, ruff, pyright clean; pytest unchanged.
- 2026-11-08: **phase 2: stored-table schemas and gates** (unstaged). Each source
  module declares the schema of its tables, built from its existing dtype map with
  `from_dtypes` (new in `skatkis.pipelines.schema`), so a dtype is stated once:
  `PRICE_SCHEMA`, `DIVIDEND_SCHEMA`, `SPLIT_SCHEMA` (`sources/prices.py`),
  `COMPANYFACTS_SCHEMA` (`sources/edgar.py`), `CONSTITUENT_SCHEMA`, `CHANGE_SCHEMA`
  (`sources/constituents.py`), `OBSERVATION_SCHEMA` (`sources/fred.py`).
  `market_data.update.TABLE_SCHEMAS` lists every stored table with its schema (the
  facts add `snapshot_as_of`; `listings` is declared there, as `update.py` builds
  it). `market_data/validation.py` holds the gate `check_table`: exactly the declared
  columns (`assert_exact_columns`, new in `skatkis.pipelines.validation`, now also
  used by `check_buyability`), then the schema checks. It runs before every
  `write_table` in `update.py` and on the stored market tables `value_investing.__main__`
  reads (corrected after inspection 2: four reads were first left ungated).
  Keys measured unique on the 2026-10-31 data before declaring them; the facts key is
  (`cik`, `accession`, `field`, `tag`, `unit`, `period_start`, `period_end`). The
  allowed fields, taxonomies, tags and units of the facts are derived from `TAG_MAP`,
  since the parser reads only those; prices and dividends must be in USD
  (`PRICE_CURRENCY`), since every later stage reads them as USD; prices, dividends and
  split ratios are positive, volume non-negative. The GICS sectors carry no allowed
  set (the only list is configuration). Not declared: `filed` on or after
  `period_end` (legitimate filings break it; market_data notes). Results: the twelve
  stored tables pass (1.4 s added to a load, almost all `facts` and `prices`); the
  gate catches a duplicate instant fact (a missing `period_start` in the key), a tag
  outside `TAG_MAP`, a missing column, a duplicate price, a close of 0, a EUR price, an
  extra column, a split denominator of 0 and a member without a sector. The 18 tables
  identical through the gated loader; Black, ruff, pyright clean; pytest unchanged.
  Not exercised: the write path of `update.py` end to end (it needs the network); it
  runs the same `check_table`.
- 2026-11-08: **inspection 2 fixes** (unstaged). `update.py` checks a company's facts
  and a symbol's prices, dividends and splits on their own first: one that fails is
  left out and reported in `UpdateResult.failed` with the reason, like a fetch or
  parse failure, and the rest of the update goes on; the combined tables are checked
  again (keys repeated across companies or symbols), all before any is written
  (`_write_all`), so a failure leaves the folder as it was. The four remaining reads
  of stored market tables in `value_investing.__main__` (prices twice, changes,
  constituents) go through the gated `_read`; the stored buyability tables are this
  tool's output with merged columns and are not gated there. Docstrings: the stale
  `STORED_TABLES` name, "dtypes are not checked" stated for `check_table`, the
  `TAG_MAP` decision in `COMPANYFACTS_SCHEMA`, `LISTING_COLUMNS`, `PRICE_CURRENCY` and
  `COMPANYFACTS_COLUMNS` in the Public API. `.claude/rules/schema-contracts.md`
  amended (Developer): a stored table's schema lives with its producer, and the
  hard-or-soft principle. Write path exercised offline into the scratchpad (stored
  snapshots, no network): `update_prices` for AAPL, MSFT and KO reproduces the stored
  rows exactly; with a close of 0 injected into MSFT, MSFT is dropped and reported and
  the other two written; the same symbol twice fails the combined check with nothing
  written. The 18 tables identical; Black, ruff, pyright clean; pytest unchanged. For
  the Tester (inspection 2): NaN in a unique key compared as equal (the instant
  facts); the empty tables through `check_table`; the per-item failure path into
  `failed`; check-all-before-write.
- 2026-11-08: **Warden fixes** (unstaged). Finding 1: the zip unstaged and git-ignored
  (`.gitignore`). Finding 2: the two update loops catch `ValueError`, which covers the
  parse errors, the schema breaches and a column mismatch, so the promise of the
  module docstring holds; exercised offline: KO with an extra price column lands in
  `failed`, AAPL is written. Finding 3: the unused `assert_*` functions
  (`assert_required_if`, `assert_no_nulls`, `assert_unique_key`,
  `assert_probability_bounds`, `assert_positive`, `assert_non_negative`,
  `assert_allowed_values`, `assert_constant_columns`) and `report.build_report`
  removed; value rules are checked only through the schema, so each is stated once.
  Finding 4: `.claude/rules/schema-contracts.md` now loads for `Toolbox/*/sources/**`
  and `market_data/update.py`. Note 9: a failed symbol is no longer also listed as
  reused. Kept for phase 3, with the reason that phase 3 (the nodes and their layer
  contracts) is where they are used: the schema vocabulary not yet used (`required_if`,
  `computable_from`, `segment`, `result`, the defaults), `Grain`, `SourceSchema`,
  `Ownership`, `bind` and its checks, `LayerContract`, `safe_merge`, and
  `segmentation_source="universe"`. The documentation items go to the Scribe (the
  `identifier` docstring among them, note 11), the tests to the Tester. Results: the 18
  tables identical; Black, ruff, pyright clean; pytest unchanged.
- 2026-11-08: **read-side schemas** (unstaged): `INPUT_TABLES` in
  `value_investing/schema.py`; `_read` uses it; `LISTING_COLUMNS`/`LISTING_SCHEMA` in
  `sources/prices.py`, `FACTS_TABLE_SCHEMA` in `sources/edgar.py`;
  `update.TABLE_SCHEMAS` built from them. The read schemas equal the write schemas
  for all seven tables read; `value_investing` no longer loads `market_data.update`
  (checked in a fresh interpreter). `.claude/rules/schema-contracts.md` and the
  `market_data/validation.py` docstring updated. The 18 tables identical; Black, ruff,
  pyright clean; pytest unchanged. Not yet reviewed by the Inspector or the Warden.
- 2026-11-08: **Scribe** (unstaged): docstrings in `skatkis/pipelines/schema.py` (stored
  tables on plain schemas; `SourceSchema` and `bind` kept for the nodes; the
  `identifier` tag marks a case-significant key, read by nothing yet), `report.py`,
  `value_investing/schema.py` (change ID removed), both `validation.py` "Raises",
  `value_investing/__main__.py`, `market_data/sources/edgar.py` (attribution removed;
  the re-parsing statement corrected to the latest snapshot per company) and
  `market_data/update.py`; `market_data/README.md` gains "Stored tables and their gate"
  (the eight tables, folder, schema, owner, key), `value_investing/README.md` a
  "Gates" section. Spec left unchanged (dtypes, an open decision). Black, ruff, pyright
  clean.
- 2026-11-08: **Tester** (unstaged): 229 new tests in `tests/skatkis/pipelines/`
  (`test_schema`, `test_contracts`, `test_validation`, `test_report`),
  `tests/market_data/` (`test_validation`, `test_update`, the update without network
  through an injected transport) and `tests/value_investing/` (`test_schema`,
  `test_validation`, `test_pipeline` end to end on AAA and BBB, `test_main`); empty
  `__init__.py` files in `tests/` so test files of the same name in different folders
  do not clash. The 14 stale `test_report.py` cases updated to `_tier(share, cutoffs)`,
  which replaced `(share, threshold, ratio)` in `85309e2` with four tiers
  (`tier_cutoffs = [0.6, 0.4, 0.2]`, user, 2026-11-02): the boundaries are asserted on
  the current tiers, since the old Amber included its lower bound and Black did not
  exist; in the worst-table test BBB moved from 0.30 to 0.50 to stay Amber. Full
  suite: **307 passed, 0 failed**; Black, ruff, pyright clean. Found, not fixed (for a
  later change, cosmetic): the `field_uniqueness` branch of `_describe_failures` is
  never reached (Pandera reports even a one-column key as
  `multiple_fields_uniqueness`); a failing frame-level check can print the same line
  twice with different row counts; with one key column missing, a duplicate-key line
  on the remaining key columns appears as well.

## Inspections

| Date | Commits | Findings | Open |
|---|---|---|---|
| 2026-11-08 | `main` (`ebe4700`)..working tree | 0 blocking, 2 should fix: constraints resting on the data in `value_investing/schema.py`; the Pandera floor in `pyproject.toml`; notes (stale registry and `preface` references in `contracts.py`, `BOUND_TOLERANCE` location) | none |
| 2026-11-08 | `main` (`a3d88b6`)..working tree (phase 2) | 0 blocking, 4 should fix: partial write on a gate failure; one bad vendor row aborting an update (per-item gate into `failed`); the `TAG_MAP` coupling on read (kept, decided); stale `STORED_TABLES` docstring; notes (ungated reads, rule text, dtypes not checked, Public API entries) | none |

## Warden report

### 2026-11-08, commit `a3d88b6` plus the working tree

**Header**
- Change: S_202611_005, pipeline schema, contracts and validation, with value_investing and market_data built on them. Kind: refactor.
- Date: 2026-11-08.
- Commit reviewed: HEAD `a3d88b6` plus the working tree. The tree is dirty: most of the work is uncommitted, staged and unstaged.
- Base: `main` (`ebe4700`), branch `feature/skatkis/s-202611-005-pipeline-schema`.
- Builds on: inspection 1 (`ebe4700`..working tree) and inspection 2 (`a3d88b6`..working tree, phase 2). Both closed with nothing open. I reviewed the inspection 2 fixes closely and the rest of the branch once.

#### Findings

**Blocking**

1. **`midas/skatkis.zip` is staged for commit** (git status `A midas/skatkis.zip`, 4.6 MB, on the branch file list).
   - Rules broken:
     - `.claude/rules/midas-records.md`: "`midas/` holds no code and no vendor data".
     - The change file's own note (2026-11-07): "`midas/skatkis.zip` is the template, untracked".
     - `AGENTS.md`, "Prohibited": material from beyond the repository.
   - Why it matters: the archive is another repository's code. It includes `KPMG_branding/kpmg_logo.png`, `branding.py`, `saspy_wrapper/` with SAS jobs (`join_r2r_prov.sas`, `Extract_entries_DQ_LG_samples.sas`), `accreditation/` and notebooks. Once merged it stays in git history.
   - Fix: `git restore --staged midas/skatkis.zip`. Keep it out of the repository or git-ignore it, and confirm with the user where the template should live.

**Should fix**

2. **A column mismatch on one company or one symbol still stops the whole update** (`Toolbox/market_data/update.py:237` and `:306`).
   - `check_table` raises a plain `ValueError` from `assert_exact_columns` when a column is undeclared or missing (`market_data/validation.py:606`). The handlers catch only `ApiError`, `EdgarParseError`/`PriceParseError` and `SchemaValidationError`.
   - So the module docstring's promise ("one that fails is left out and reported in `UpdateResult.failed`", `update.py` lines 318–324) holds for constraint breaches but not for column problems.
   - Unlikely today, because the parsers build their columns by construction, but the documented contract is broken.
   - Fix (Developer): either make `check_table` raise one exception type for both, or catch `ValueError` in the two loops. Then state the behaviour in the `check_table` "Raises" section.
3. **Generic code with no user and no recorded reason** (Inspector item 8; done-when "no template code the repository does not use").
   - `skatkis/pipelines/validation.py` has `assert_required_if`, `assert_no_nulls`, `assert_unique_key`, `assert_probability_bounds`, `assert_positive`, `assert_non_negative`, `assert_allowed_values` and `assert_constant_columns`. Nothing calls them; only `assert_exact_columns` and `assert_required_columns` are used.
   - They state each rule a second time, next to the Pandera translation in `to_pandera_schema`. The two copies already differ: the assert versions name no sample keys, which `.claude/rules/validation.md` asks for.
   - `skatkis/pipelines/report.build_report` is also unused. `pipeline.py:419` builds `PipelineReport(notices=...)` directly, and the name clashes with `market_data.report.build_report` and `value_investing.report.build_report`.
   - The kept-for-phase-3 list in the change file (inspection 1 fixes) covers the vocabulary, `LayerContract`, `bind` and `segmentation_source`, but not these.
   - Fix: remove them (Developer), or have the Secretary add them to the kept list with the reason.
4. **The amended rule does not load where it applies** (`.claude/rules/schema-contracts.md`).
   - Its new paragraph governs the schemas in `market_data/sources/*.py` and `TABLE_SCHEMAS` in `market_data/update.py`.
   - Its `paths:` cover only `Toolbox/*/schema.py`, `Toolbox/*/contracts.py` and `Toolbox/skatkis/pipelines/**`, so it is never loaded when those files are edited.
   - Fix (Developer): add `Toolbox/*/sources/**/*.py` and `Toolbox/market_data/update.py` to `paths:`, or move the paragraph to `.claude/rules/sources.md`.
5. **Housekeeping: change file, design and change log are behind the decisions** (`secretary.md`, "Working on a change"; Warden item 7).
   - **Status:** `agreed` in the change file and in `CHANGELOG.md:19`. The build is done, so it should be `in progress`.
   - **"Done when", line 261:** says "with tests". The Tester comes after this report, so "with tests" belongs to closing, not the PR.
   - **"Done when", line 265:** says "Every `market_data` cleaned table has a `SourceSchema` and binds without findings". The 2026-11-08 phase 2 amendment replaced this with a plain schema per stored table and gates; `SourceSchema` and `bind` are deferred to phase 3. Reword to match.
   - **Agreed approach, step 5.2:** still describes `SourceSchema` and binding, and lists `universe` as a stored table. `universe` is built in memory by `index_universe` and has no schema. Point the step at the amendment.
   - **Design, target layout:** lists `report_checks.py`, which was not ported, plus `Toolbox/market_data/schema.py` and `Toolbox/value_investing/contracts.py`, neither of which exists. The real layout is per-source schemas, `market_data/validation.py` and `value_investing/validation.py`.
   - **Design, step 4:** says "Declare the `market_data` `SourceSchema`s and bind them in the update and check commands". Bring it up to date.
   - **Design, step 3:** names `check_buyability` correctly. Steps 4 and 5 should name `TABLE_SCHEMAS`, `check_table` and `_write_all`.
   - **Inspection 2 behaviour change not recorded as a decision:** the update now drops a failing company or symbol into `failed` and checks every table before writing any. This changes what the update accepts (`.claude/rules/validation.md`: "Changing what a gate accepts or rejects is a behaviour change … say so"). It is in Notes only; if the user agreed it, add a dated entry under Decisions.

**Notes**

6. **Refactor label.** The 18 buyability tables are identical and `regression_check` is `unchanged`, so the label holds for every result (`AGENTS.md`, "Methodology vs refactor"). The new write and read gates do change behaviour on bad data, though: an update that `main` would have written can now drop a company or symbol, or refuse a table. One consequence decided on 2026-11-08: after a `TAG_MAP` change, an older as-of folder's facts are refused on read until they are parsed again. Say so in the PR description.
7. **The value tool imports the update module** (`value_investing/__main__.py:2235`). It reads `TABLE_SCHEMAS` from `market_data.update`, which also pulls in the API clients and providers. The amended rule puts `TABLE_SCHEMAS` there on purpose, so this is not a rule breach. A small `market_data` module holding the stored-table schemas, read by both `update.py` and `__main__.py`, would separate reading from writing. For the user to decide, possibly in phase 3.
8. **Ungated reads remain.**
   - `market_data/checks.py:178–201` and `:259` (the `check` command) read facts, prices, dividends, constituents, splits and observations without the gate. Its own `duplicate (symbol, date)` and `close <= 0` counts now duplicate `PRICE_SCHEMA`.
   - `market_data/__main__.py:166` reads the constituents just written, which is acceptable.
   - Callers that pass their own `Tables` to `pipeline.buyability` (MCP tools, notebooks) get the output gate but no input gate (`AGENTS.md`, "Contracts and gates").
   - The 2026-11-08 phase 2 decision scopes the gates to the update writes and the `value_investing` loads, so none of this breaks a rule. Worth a note in `midas/toolbox/market_data/notes.md` for phase 3.
9. **A stored symbol that fails its gate is listed as reused and as failed.** `update_prices` builds `reused=tuple(stored)` without removing failed tickers (`update.py:320`). `fetched` does exclude them. Cosmetic.
10. **The spec and the code disagree on dtypes.** Spec §6.1 says a node's `schema` holds "expected output columns, dtypes and index; validated after every run". The gates check columns and constraints, not dtypes (stated in `validate_from_schema` and `check_table`). This is not a defect for this slice, but it is a contradiction to record (`AGENTS.md`, "Authority order") until phase 3 decides.
11. **The `identifier` tag does nothing.** Its docstring (`skatkis/pipelines/schema.py:75`) says the case is kept "when cast (other strings are lower-cased)". `cast_and_fill` was not ported, so nothing casts. The tag is used in every new schema.

**Inspections closed.**
- Inspection 1: every finding is fixed or recorded (Pandera floor, constraint split by source, `BOUND_TOLERANCE` location, `contracts.py` references).
- Inspection 2: partial write fixed (`_write_all`); per-item gate fixed, except the column-mismatch gap in finding 2; `TAG_MAP` coupling decided and recorded; `STORED_TABLES` removed (no matches left); four reads gated; rule text amended; "dtypes not checked" stated; Public API entries added.

**Code on the uninspected fixes** (Inspector items 1–7):
- Contracts and gates: `_write_all` checks every table before writing any (`update.py:435–444`), and the per-item gates sit inside the fetch loops. Apart from finding 2, they behave as the module docstring says.
- Determinism, point-in-time and look-ahead: nothing changed by the diff.
- No keys or vendor data in the code.
- Black, ruff and pyright are clean.
- No new `noqa`; the one on `update_constituents` predates the branch and carries its reason.

#### Not checked

- `.vscode/settings.json` changed on the branch, but it was left out of the diff. Not reviewed.
- The `update.py` write path against the network. It was exercised offline from stored snapshots for AAPL, MSFT and KO only. `update_edgar` and `update_constituents` were not run through their new gates end to end.
- Empty tables through `check_table` (an update with no companies, `_empty_facts`). Not in the check output.
- A plain `ValueError` from `assert_exact_columns` inside a per-item loop (finding 2). Read from the code, not run.
- The cost of the output gate in `value_investing.lookahead`, which calls `buyability` repeatedly. `tests/value_investing/test_lookahead.py` passes; its timing was not measured.
- The report summaries are not part of the baseline (change file, Notes, 2026-11-08). The agreed approach, step 7, asks for "report summaries … identical". Only the 18 buyability tables (table, weights, correlations) were compared.
- The template code itself, beyond spot checks for leftover loan, KPMG, registry and SOP references (none in `Toolbox/`). The ports were reviewed by the two inspections.
- `regression_check` covers only the BTC harness, as the caller noted.

#### Documentation to update (Scribe)

- **`Toolbox/market_data/README.md`, "Updating the data" (lines 136–161):**
  - Every table passes its schema before it is written.
  - A company or symbol that fails is left out and listed under `failed` in the printed summary.
  - The combined tables are all checked before any is written.
  - Prices and dividends must be in USD (`PRICE_CURRENCY`).
  - The facts read gate refuses a table parsed under an earlier `TAG_MAP`.
  - Also a short list of the stored tables with their keys.
- **`Toolbox/value_investing/README.md`:**
  - The buyability output gate (`check_buyability`), with exactly the declared columns.
  - `Buyability.report` and the soft expectations on `market_cap` and `pb`, printed by `buyability`.
  - The gated reads of the stored tables.
- **`Toolbox/value_investing/__main__.py` module docstring:** the stored tables are checked as they are read (`_read`), and `buyability` prints each view's pipeline report.
- **`Toolbox/value_investing/schema.py` module docstring (lines 2437–2444):** it says some constraints rest on the stored tables "until the source schemas check them (S_202611_005, phase 2)". Phase 2 now checks a positive `close` (`PRICE_SCHEMA`) and a required `gics_sector` (`CONSTITUENT_SCHEMA`). Update the sentence, and drop the change ID from official documentation (`AGENTS.md`, "Authority order").
- **`Toolbox/skatkis/pipelines/schema.py` module docstring (lines 7–11):** it says a tool declares "one `SourceSchema` per stored table; `bind` checks them". Stored tables now use plain schemas built with `from_dtypes`; `SourceSchema` and `bind` wait for phase 3. Also the `identifier` docstring (line 75), finding 11.
- **`Toolbox/skatkis/pipelines/report.py`:** the `PipelineReport` docstring says it is "built by `build_report`", but `pipeline.py` builds it directly. Lines 110–111 speak of "a stored report", and nothing stores one.
- **`Toolbox/value_investing/validation.py` `check_buyability`, "Raises" (lines 2639–2643):** a missing column raises `ValueError` from `assert_exact_columns` before Pandera runs, so `SchemaValidationError` is not raised for a missing column. The same applies to `market_data/validation.py` `check_table`.
- **`.claude/rules/schema-contracts.md` (Developer, not Scribe):** the `paths:`, finding 4. The `market_data/sources/*` docstrings reference `.claude/rules` nowhere, which is fine.
- **Spec §6.1, `docs/value_investing_bot_spec.md:227`:** dtypes are not yet validated (finding 10). Record it as a known gap, or leave it for the user to decide in phase 3.
- **Official documentation must not cite change IDs or Midas records** (`AGENTS.md`, "Authority order"). The code docstrings cite `S_202611_005` in `.claude/rules/schema-contracts.md` (rule text, acceptable) and `value_investing/schema.py` (official, remove). `edgar.py` cites "(user, 2026-11-08)" in `COMPANYFACTS_SCHEMA`; restate it as the rule without the attribution.

#### Tests to write (Tester)

Mirror the source tree (`.claude/rules/tests.md`), with synthetic tickers and no network. `tests/value_investing/test_report.py` has 14 stale failures from `main` (`_tier` takes two arguments); they are for the Tester to fix, not caused by this branch.

`tests/skatkis/pipelines/test_schema.py`:
- `from_dtypes`: keeps the column order; rejects tags for undeclared columns.
- `PipelineSchema`: rejects a column produced by two layers, and a column that is both input and output; `outputs` carries `produced_by`.
- `metadata`, `layer_outputs`, `required`, `expected`.
- `BOUND_TOLERANCE` value.

`tests/skatkis/pipelines/test_contracts.py`:
- `safe_merge` on conflicting and agreeing entries (or nothing, if it is removed under finding 3).

`tests/skatkis/pipelines/test_validation.py`:
- `validate_from_schema` reports every kind of violation in one error: required null, duplicate key, positive, non-negative, probability, allowed values, `required_if`, missing key column, missing allowed-values column. Sample rows are named by key values.
- The caller's frame is unchanged, values and dtypes (Inspector 1).
- A real Pandera failure reaches `SchemaValidationError.failure_cases` (Inspector 1).
- The Pandera check names `_describe_failures` relies on: `column_in_dataframe`, `not_nullable`, `field_uniqueness`, `multiple_fields_uniqueness` (Inspector 1).
- Repeated row labels are checked on a renumbered copy, with samples by position.
- NaN in a unique key compares as equal (two instant facts with no `period_start`) (Inspector 2).
- Boundaries: $1 + 10^{-13}$ passes and $1 + 10^{-11}$ fails `probability`; $-10^{-13}$ passes and $-10^{-11}$ fails `non_negative`; 0 fails `positive`; nulls pass value checks.
- `assert_exact_columns`: undeclared column, missing column, any order.
- The remaining `assert_*` functions, if kept (finding 3).

`tests/skatkis/pipelines/test_report.py`:
- `soft_violations` and `expectation_notices` for each `expect_*` flag, with the tolerance.
- A clean table gives no notices.
- `summary()` text.
- `to_dataframe` on an empty report keeps its columns.

`tests/market_data/test_validation.py`:
- `check_table` passes a clean table and an empty table for every entry of `TABLE_SCHEMAS` (Inspector 2).
- It rejects an extra column and a missing column (`ValueError`).
- It rejects a duplicate key per table: the facts key with `period_start` missing, prices (`symbol`, `date`), dividends (`symbol`, `ex_date`), splits, listings, constituents (`symbol`), observations (`series_id`, `date`).
- It rejects a close of 0, a EUR price, a split denominator of 0, a member with no sector, a tag outside `TAG_MAP`, and an empty `snapshot_as_of`.

`tests/market_data/test_update.py`, with a fake provider or recorded snapshots:
- Per-item failure: a company with a bad fact, or a symbol with a close of 0, goes to `failed` with its reason, and the others are written (Inspector 2).
- Check-all-before-write: the same symbol twice fails the combined check, and nothing in the folder changes, including tables already present (Inspector 2).
- A column mismatch per item (finding 2), once the Developer settles the behaviour.
- `fetched` excludes failed tickers.

`tests/value_investing/test_validation.py` and `test_schema.py`:
- `pipeline_schema` builds the columns of the configured rules and buckets.
- An unknown rule raises `KeyError`.
- `buyability_schema` keys on `KEY`.
- `check_buyability` rejects an extra column, a missing column, a flag of 0.5, a grade equal to `buckets`, a duplicate (`symbol`, `date`), a negative close, a missing `gics_sector`; a `score_weighted_share` of $1 + 2.2 \times 10^{-16}$ passes.

`tests/value_investing/test_pipeline.py`:
- `buyability` on a small fixture returns a `Buyability` whose `report` lists a negative `market_cap` or `pb` as a notice and does not raise.

`tests/value_investing/test_main.py`:
- `_read` gates a stored table and raises on a corrupted one.
- `_company_names` reads through the gate.

#### Draft outcome (from the change file)

> **Outcome (draft).** Done on <date>, commit <sha>. `skatkis.pipelines` now has the schema vocabulary, `PipelineSchema`, `SourceSchema`, `bind`, `LayerContract` and `safe_merge`, schema-driven validation on Pandera (0.35.0, adopted by the user on 2026-11-07), and `Notice`/`PipelineReport`, ported from the enterprise template. The loan-specific parts were removed. The template's branding, Office, SAS, accreditation, fault-injection and steward code was dropped (user, 2026-11-07). `report_checks.py`, `sources.py`, `utils.py` and `cast_and_fill` were not ported. Execution stays the spec §6 node graph (S_202611_003).
>
> Phase 1: `value_investing.schema` declares the buyability columns per layer, and `pipeline.buyability` runs the output gate `check_buyability`, so every caller is gated. Constraints that hold by construction are hard. `market_cap` and `pb`, which rest on EDGAR's first-reported share counts, are soft expectations reported in `Buyability.report` (user, 2026-11-08). The [0, 1] and non-negative bounds allow `BOUND_TOLERANCE = 1e-12`, after `score_weighted_share` reached $1 + 2.2 \times 10^{-16}$ on nine rows (user, 2026-11-08). Clipping in `scoring` was rejected because it would move the baseline.
>
> Phase 2 was amended (user, 2026-11-08). The template's `bind` assumes one namespace of value columns joined by key, which the stored tables do not fit: names repeat across stages, the facts are long-form, and `rule_inputs` aligns point in time. So each stored table has a schema in its source module, built with `from_dtypes` and listed in `market_data.update.TABLE_SCHEMAS`, with the gate `check_table` where `update.py` writes and where `value_investing` reads. `SourceSchema` and `bind` wait for phase 3. Rejected: the full binding (renamed columns, facts pivoted wide) and stopping after phase 1.
>
> The facts read gate keeps the `TAG_MAP` sets, so a facts table parsed under an earlier map is refused until parsed again (user, 2026-11-08). The update gates each company and symbol on its own, reports failures in `UpdateResult.failed`, and checks all tables before writing any.
>
> Results: the buyability table, weights and correlations of the S&P 500, 400 and 600 in both views (18 tables) are identical to `main` `ebe4700`. `regression_check` is unchanged. The twelve stored tables of 2026-10-31 pass the gate, adding 1.4 s to a load, and nine corrupted tables are rejected. Black, ruff and pyright are clean. pytest: 62 passed, with the 14 stale failures in `test_report.py` from `main`.
>
> Two inspections ran, with no findings left open, then the Warden review on 2026-11-08. Still open: the naming of the `(field, lag)` history (before phase 4) and the fate of the node registry (phase 3).

## Kickoff prompt

Pick up S_202611_005. Read the agreed approach and the design, record the baseline
(buyability tables of the three indices, `regression_check`), then port
`schema.py`, `contracts.py`, `validation.py` and `report.py` from the template with
the loan-specific parts removed, and declare the `value_investing` schema.

## Done when

- `skatkis.pipelines` has the ported modules and no template code the repository does
  not use, except what is kept for phase 3 with its reason (Notes).
- `value_investing` declares its `PipelineSchema` and the buyability output is
  asserted against it.
- Every stored `market_data` table has a schema in its source module (or in
  `update.py` for the tables the update builds) and passes the gate where it is
  written and where `value_investing` reads it.
- The baselines are unchanged.
- At closing: the Tester's tests (Warden report, "Tests to write") pass.
