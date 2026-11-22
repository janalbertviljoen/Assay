# value_investing change log

Planned changes to the value-investing tool (`Toolbox/value_investing/`). Prefix `VI`.
Naming and workflow: `midas/instructions/secretary.md`. The methodology is in
`docs/value_investing_bot_spec.md`.

## Open

| ID | Title | Kind | Status | Priority | Depends on |
|---|---|---|---|---|---|
| [VI_202610_002](changes/VI_202610_002-rule-catalogue.md) | Rule catalogue in the tool: G, E, B, M and Q rules as SOP layers, registry and config | new capability | in progress | medium | S_202610_001, S_202610_005, MD_202610_002 |
| [VI_202610_003](changes/VI_202610_003-signal-evaluation.md) | Signal evaluation: horizon returns, paper wallet and model score | new capability | in progress | high | VI_202610_002 |
| [VI_202610_004](changes/VI_202610_004-ranked-wallet-binned-score.md) | Ranked wallet and binned score | new capability | in progress | high | VI_202610_002, VI_202610_003 |
| [VI_202610_005](changes/VI_202610_005-return-correlation-weights.md) | Rule weights from past return correlation, NI1 and the universe on the date | methodology | in progress | high | VI_202610_004 |
| [VI_202610_006](changes/VI_202610_006-value-report.md) | Value report: buy-and-hold picks, value over time, rules behind the winners | new capability | in progress | high | VI_202610_005 |
| [VI_202610_007](changes/VI_202610_007-pick-price-history.md) | Price history of the picks in the value report | new capability | in progress | high | VI_202610_006 |
| [VI_202610_008](changes/VI_202610_008-conservative-and-unicorn-hunter.md) | Two strategies: the conservative picker (S&P 500 top 5, twice a year) and the unicorn hunter (top 20 of all companies, quarterly) | methodology | in discussion | high | MD_202610_004, S_202610_008 |
| [VI_202610_009](changes/VI_202610_009-unit-tests.md) | Unit tests for the value tool and the market data it reads | tests | ready | high | VI_202610_002 to 007, MD_202610_004 |
| [VI_202611_001](changes/VI_202611_001-model-calibration.md) | Model calibration: signed rule weights, point curves per rule, fitted cut-offs, sampled studies | methodology | in progress (first light) | high | S_202611_003 |
| [VI_202611_002](changes/VI_202611_002-report-general-sells.md) | Report: general worst list, sells tracked in the wallet's cash flows | new capability | in progress | medium | VI_202610_006 |

## Done

| ID | Title | Done |
|---|---|---|
| [VI_202611_003](changes/done/VI_202611_003-personal-buy-list.md) | Personal buy list with price curves in the S&P 500 report | 2026-11-22 |
| [VI_202611_004](changes/done/VI_202611_004-blended-dip-weighting.md) | Blended rank and dip weighting of the wallet's purchases (not adopted) | 2026-11-19 |
