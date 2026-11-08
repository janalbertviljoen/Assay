# S_202611_005: design

Target structure for the first slice. Decisions and history are in the
[change file](../changes/S_202611_005-pipeline-schema-and-contracts.md).

## Target layout

```text
Toolbox/skatkis/pipelines/
├── schema.py        vocabulary, Grain, PipelineSchema, SourceSchema, ownership, bind
├── contracts.py     LayerContract, safe_merge
├── validation.py    assert_* functions; schema-driven validation on Pandera
├── report.py        Notice, PipelineReport
└── report_checks.py generic checks over sources (as the template, if used)
Toolbox/market_data/schema.py        SourceSchema per cleaned table
Toolbox/value_investing/schema.py    PipelineSchema: inputs and layer outputs
Toolbox/value_investing/contracts.py LayerContract per layer
tests/skatkis/pipelines/             mirrors the above
```

`sources.py` (`LookupModel`, `ColumnMap`) is ported only if a `market_data` table needs
a column map; the cleaned tables are already on canonical names, so phase 2 may need
`SourceSchema` and `bind` alone. Decide when phase 2 starts.

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
   in `pipeline.py`'s caller (`__main__`), not inside the calculation.
4. Declare the `market_data` `SourceSchema`s and bind them in the update and check
   commands.
5. Black, ruff, pyright, `regression_check`; compare the buyability tables.
6. Inspector at the milestone; Warden before the pull request; Scribe; Tester.
