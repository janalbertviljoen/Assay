# S_202611_005: design

Target structure for the first slice. Decisions and history are in the
[change file](../changes/S_202611_005-pipeline-schema-and-contracts.md).

## Target layout

```text
Toolbox/skatkis/pipelines/
├── schema.py        vocabulary, from_dtypes, BOUND_TOLERANCE, Grain, PipelineSchema,
│                    SourceSchema, ownership, bind (the last three for phase 3)
├── contracts.py     ColumnMeta, Schema, LayerContract, safe_merge
├── validation.py    assert_exact_columns, assert_required_columns; validate_from_schema
│                    on Pandera
└── report.py        Notice, PipelineReport, the soft-expectation scan
Toolbox/market_data/sources/*.py     the schema of each source's tables (PRICE_SCHEMA, ...)
Toolbox/market_data/update.py        TABLE_SCHEMAS (every stored table), the gated writes
Toolbox/market_data/validation.py    check_table, the stored-table gate
Toolbox/value_investing/schema.py    PipelineSchema: inputs and layer outputs
Toolbox/value_investing/validation.py check_buyability, the output gate
tests/                               mirrors the above
```

`sources.py` (`LookupModel`, `ColumnMap`), `report_checks.py` and `utils.py` are not
ported: the stored tables are already on canonical names and typed, so no column map or
casting is needed. The template's `bind` does not fit the stored tables (change file,
Decisions, "phase 2 amended").

## From the template, and what changes

| Template | Here |
|---|---|
| Grain `loan_id`, `mob` | `symbol`, `date` (broadcast for config-wide values) |
| Schema flags (`required`, `positive`, `probability`, `expect_*`, `owned_by`, …) | Kept; `type_rate` and the loan defaults (`default_exposure`) removed |
| Pandera translation in lazy mode, one `SchemaValidationError` | Kept; nulls pass value checks unless required, nothing coerced, unknown columns allowed |
| `bind` with one `BindingError` of all `Finding`s | Kept unchanged |
| `LayerContract.model_joins`, `immutable_inputs` | Kept; `model_joins` is empty until a layer joins a segmented table |
| Registry holding models and contracts | Phase 3, with the nodes |

## Layers and grain (value_investing)

| Layer | Grain | Produces |
|---|---|---|
| `rule_inputs` | `symbol`, `date` | price and the annual history |
| `valuation` | `symbol`, `date` | the shared ratios |
| `rules.<ID>` (G1–G7, E1–E6, GN, NN, B1–B5, M1, Q1–Q3) | `symbol`, `date` | `<id>_value`, `<id>_pass` |
| `points` | `symbol`, `date` | `<id>_points` |
| `score` | `symbol`, `date` | `score`, `score_<F>`, binned and weighted scores, `n_passed`, `n_available` |
| `weights` | `date`, `rule` | learned weights and rank correlations |
| `score_ic` | `symbol`, `date` | the learned score |

In phase 1 the schema describes the existing `buyability` table only; the layers are
not yet split, so contracts are declared but not enforced between layers.

## Steps

1. Record the baseline (change file, Notes).
2. Port `schema.py`, `contracts.py`, `validation.py` and `report.py` with the
   loan-specific parts removed; docstrings in the repository structure. The template's
   `utils.py` is not ported: its flag accessors are private helpers in `validation.py`,
   and `cast_and_fill` waits until a source needs casting.
3. Declare the `value_investing` schema and assert the `buyability` output against it
   with the output gate (`value_investing.validation.check_buyability`), run at the end
   of `pipeline.buyability` so every caller is gated.
4. Declare the schema of each stored table in its source module, list them in
   `market_data.update.TABLE_SCHEMAS`, and gate them with `check_table`: per company
   and per symbol inside the update loops (a failure goes to `UpdateResult.failed`),
   then all combined tables before any is written (`_write_all`), and on every stored
   table `value_investing` reads (`_read`).
5. Black, ruff, pyright, `regression_check`; compare the buyability tables; exercise
   the gates on corrupted tables and the write path offline.
6. Inspector at the milestone; Warden before the pull request; Scribe; Tester.
