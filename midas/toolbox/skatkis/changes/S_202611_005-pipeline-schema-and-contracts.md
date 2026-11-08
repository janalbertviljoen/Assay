# S_202611_005: Pipeline schema, contracts and validation, and value_investing on them

| Field | Value |
|---|---|
| Status | agreed |
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
   2. The `market_data` cleaned tables (`facts`, `prices`, `dividends`, `splits`,
      `listings`, `universe`) are declared as `SourceSchema` and bound, so ownership,
      requirement and grain problems are found before any data is used.
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

## Open decisions (user)

- Whether the node registry (S_202611_003) is renamed or absorbed once phase 3 starts.
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

## Kickoff prompt

Pick up S_202611_005. Read the agreed approach and the design, record the baseline
(buyability tables of the three indices, `regression_check`), then port
`schema.py`, `contracts.py`, `validation.py` and `report.py` from the template with
the loan-specific parts removed, and declare the `value_investing` schema.

## Done when

- `skatkis.pipelines` has the ported modules, with tests, and no template code the
  repository does not use.
- `value_investing` declares its `PipelineSchema` and the buyability output is
  asserted against it.
- Every `market_data` cleaned table has a `SourceSchema` and binds without findings.
- The baselines are unchanged.
