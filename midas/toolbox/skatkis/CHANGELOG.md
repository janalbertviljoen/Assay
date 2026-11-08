# skatkis change log

Planned changes to the shared core (`Toolbox/skatkis/`), Midas's index server and the
repository setup. Prefix `S`. Naming and workflow: `midas/instructions/secretary.md`.

## Open

| ID | Title | Kind | Status | Priority | Depends on |
|---|---|---|---|---|---|
| [S_202610_002](changes/S_202610_002-midas-index-server.md) | Midas index server with `index` and `lab` profiles | tooling | ready | high | S_202610_001 |
| [S_202610_003](changes/S_202610_003-numpydoc-docstrings.md) | Docstrings to the numpydoc structure (Owns, Must not, Public API, Computes) | documentation | ready | medium | S_202610_001 |
| [S_202610_004](changes/S_202610_004-claude-code-guard.md) | Claude Code permissions, protected files and post-edit hook | tooling | in discussion | medium | none |
| [S_202610_005](changes/S_202610_005-repository-sop.md) | Repository SOP and README | documentation | ready | low | S_202610_001 |
| [S_202610_007](changes/S_202610_007-market-analysis-plots.md) | Market analysis plots: metrics over time, coverage and spread, generic on any column | new capability | in progress | high | MD_202610_001 |
| [S_202610_006](changes/S_202610_006-portfolio-backtest-engine.md) | Multi-asset portfolio backtest engine (wallet) | new capability | in discussion | high | S_202610_001, spec §9.4 |
| [S_202611_002](changes/S_202611_002-midas-investor-hat.md) | Midas, the investor hat, with a Graham reference and the starting investor profile | new capability | agreed | medium | S_202610_002 |
| [S_202610_008](changes/S_202610_008-midas-wrath-scenario-testing.md) | Midas's wrath: scenario testing of a model (survivorship experiment and input tests; market scenarios later) | new capability | agreed | high | MD_202610_004 |
| [S_202611_003](changes/S_202611_003-calibration-infrastructure.md) | Calibration infrastructure: pipeline nodes, cache, studies and searchers | new capability | agreed | high | none |
| [S_202611_005](changes/S_202611_005-pipeline-schema-and-contracts.md) | Pipeline schema, contracts and validation (from the enterprise template), and value_investing on them | refactor | in progress | high | none |

## Done

| ID | Title | Done |
|---|---|---|
| [S_202610_001](changes/done/S_202610_001-repository-layout.md) | Repository layout: `Toolbox/`, `skatkis`, sandbox, notebooks | 2026-10-31 |
| [S_202611_001](changes/done/S_202611_001-agent-instructions-slimmed.md) | Agent instructions slimmed and roles split (inspector, scribe, tester) | 2026-11-01 |
