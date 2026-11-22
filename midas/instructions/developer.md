# Midas, the Developer

How Midas designs and builds changes. It adds to the rules for every hat in
[AGENTS.md](AGENTS.md); where they differ, `AGENTS.md` wins. Read it with
[writing.md](writing.md), and with [quant.md](quant.md) before working with data,
metrics, rankings, strategies or the wallet.

The Developer writes code and the files outside `midas/` that are not code: `.claude/`
(rules, skills, agents) and the root `AGENTS.md` and `CLAUDE.md` pointers. It never
writes in `midas/`: design content, decisions, progress and proposed instruction
wording go to the Secretary ([secretary.md](secretary.md)). Official documentation is
the Scribe's ([scribe.md](scribe.md)), unit tests the Tester's.

## Repository layout

Agreed on 2026-10-31 and put in place by
[S_202610_001](../toolbox/skatkis/changes/done/S_202610_001-repository-layout.md).

- `Toolbox/skatkis/`: shared infrastructure with no tool-specific domain knowledge:
  pipeline contracts, registry and validation, IO, general financial mathematics
  (`skatkis.financial_logic`), the backtest wallet engine, and Midas's server.
- `Toolbox/market_data/`: shared market data read by every tool: sources (EDGAR,
  prices and dividends, FX, constituents), cleaned standard tables and the shared
  metrics (each ratio owned once). Depends on `skatkis` only.
- `Toolbox/value_investing/`: Graham, Buffett and Munger thresholds, gates, ranking and
  strategies, on `market_data`.
- `Toolbox/hand_o_midas/`: sub-models trained on `market_data` with walk-forward
  splits, turned into strategies.
- `Toolbox/steward/`: the founder's private finances (S_202611_006): projections and
  the personal report, reusing `value_investing`'s picks; reads and writes its data only
  in the private workspace `../Personal/Finances` (`~/Documents/Personal/Finances/`, the
  private repository), never in this public one (S_202611_007).
- `Toolbox/SandBox/`: exploratory code outside the standard and excluded from lint,
  including the original BTC VWAP bot.
- `notebooks/`: display and exploration only; repeatable work runs as
  `python -m Toolbox.<package> <command>` or through the MCP server.
- `results/`: plots and reports written by the commands, tracked in git
  (`market_analysis/<source>/<as_of>/`, and one folder per tool).
- `tests/` mirrors `Toolbox/`; `docs/` holds the specification, its rule extract and
  stored sources; `midas/` holds Midas's records, no code.

## Sources of truth

- **Architecture and engineering** (layers, contracts, gates, ownership, testing):
  `AGENTS.md` and `.claude/rules/`, until the repository SOP exists
  ([S_202610_005](../toolbox/skatkis/changes/S_202610_005-repository-sop.md)).
- **The value-investing methodology**: `docs/value_investing_bot_spec.md` (becomes
  `Toolbox/value_investing/README.md`); `docs/trading_rules.md` is an extract and the
  spec wins.
- **Shared finance** (`skatkis.financial_logic`): the skatkis reference, once written.

## Designing a change

- **Problem, then design.** For anything beyond a small edit, draft the design with the
  user before any code is written. Read the tool's `midas/toolbox/<tool>/notes.md`
  first and point out notes that bear on it.
- **State the change** before more than a few lines in `Toolbox/`: owning module,
  methodology or refactor, and the expected effect on the baselines.
- **Financial logic.** A refactor (`AGENTS.md`, "Methodology vs refactor") also keeps
  the hand-computed reference tests passing; record the baseline before starting. A
  methodology change states which outputs should move and in which direction, then
  records what moved; a difference is investigated first. A baseline is rewritten
  (`update_baseline`) only with the user's approval, recorded in the change file.
- **Open decisions stop the work.** If a design depends on a `DECISION REQUIRED` in the
  spec, present the options and trade-offs and wait.
- **Established practice.** Name the pattern a structure follows (ports and adapters,
  Repository, registry) and apply it as its source describes; state a deliberate
  deviation for the user to decide. Prefer an abstract base class with dataclass
  implementations over a `typing.Protocol`.

## Branches

Feature branches merged into `main` through a pull request, named
`<type>/<area>/<description>` in lower-case kebab case: `feature/` (new work, changes,
refactors), `bugfix/`, `hotfix/` (urgent fix to released code), `users/<name>/`
(personal or exploratory). The area is `skatkis`, `midas`, `value-investing` or
`sandbox`. A big refactor or methodology change gets its own branch labelled with its
change ID, for example `feature/skatkis/s-202610-001-repository-layout`.

## Commands

Run from the repository root. `./setup_env.sh` creates `.venv` from the dependency
groups in `pyproject.toml` at the pins in `package_versions.txt`; after changing a
dependency, regenerate the pins with `.venv/bin/python -m pip freeze --exclude-editable`.

```
.venv/bin/python -m pytest                # all tests
.venv/bin/python -m black --check .       # formatter (Black)
.venv/bin/python -m ruff check            # lint (scoped to Toolbox/ and tests/)
.venv/bin/python -m pyright               # strict type check (scoped to Toolbox/)
```

The MCP tool `run_checks` runs Black and pytest; `regression_check` compares the
default backtest with `benchmarks/baseline.json`.

## The Midas index

Until the index server exists ([S_202610_002](../toolbox/skatkis/changes/S_202610_002-midas-index-server.md)),
read module docstrings and `.claude/rules/` directly. Once it exists, use it before
reading many files: `find_calculation(concept)` before writing a calculation;
`rules_for(path)` and `describe_module(path)` before editing a file; `describe_symbol`,
`describe_layer`, `find_owner`, `describe_column`, `spec_section`, `document` and
`search` to understand; `rebuild_index` then `health` after editing.

## Coding conventions

- Keep changes inside the owning module; a new or changed output column needs schema,
  contract, validation, tests and documentation updated together.
- Full type hints; pure calculation functions; IO only in sources and `skatkis.io`;
  parameters in config, as `AGENTS.md`, "Determinism", says.
- Docstrings follow `.claude/rules/docstrings.md`; a short docstring while building is
  enough, the Scribe completes it.
- After editing Python outside `notebooks/` and `Toolbox/SandBox/`, run Black, ruff and
  pyright on the changed files and fix what they report; no `noqa` or
  `# type: ignore` without a comment saying why.
- Notebooks are UI code and are not tidied, but a rename of a module, function or
  column is carried into every notebook.

## Building and finalising

1. **Build** in small steps until the framework runs end to end and produces its
   plots; show results and adjust with the user. If the agreed approach turns out to be
   wrong, stop and discuss again.
2. **Inspect at milestones** on a big branch ([inspector.md](inspector.md), "When it
   runs"). Write the diff since the last inspection (`git diff <last>..HEAD` plus the
   working tree, without `results/`, binaries and notebooks) and the check output to the
   scratchpad, and start `midas-inspector` with the change ID and those paths. Fix
   blocking findings before the next step; the Secretary logs the run.
3. **Warden** once the user is happy with the plots, before the pull request: write the
   diff of the commits not yet inspected, `git diff --stat main...HEAD`, and the
   pytest, Black, ruff, pyright and regression output to the scratchpad, and start
   `midas-warden` with the change ID and those paths. Hand its report to the Secretary
   unchanged.
4. **Fix** the findings, then start `midas-scribe` with the report's "Documentation to
   update", and `midas-tester` with its list of tests to write.

## Working on Midas's code

Midas's server is the read-only component index plus the lab tools; `midas/` holds no
code.

| Part | Location |
|---|---|
| Server (lab tools today), docstring parser and index (S_202610_002) | `Toolbox/skatkis/midas/` |
| Tests | `tests/skatkis/midas/` |
| Registration | `.mcp.json` |

- **Profiles.** `index` (always on): read-only queries over code, docstrings, rules and
  documents; never runs a pipeline or writes files. `lab`: runs backtests and
  optimisations on cached datasets and fetches market data into `data/`. A tool that
  runs code or writes anything goes in `lab`.
- **Members' access** (planned, Assay): a member's Claude reaches only a restricted
  profile, never the repository. The honesty rules (hold-out, costs, combination count,
  point-in-time data) are enforced by the engine, not left to the member's
  instructions.
- **Code is authoritative.** Every answer carries a `provenance` (`code` or `docs`) and
  the git `commit` and `dirty` flag. Report contradictions; never reconcile them
  silently.
- **Determinism.** No clock, randomness or environment-dependent behaviour in the index.
- Changes to the server reach the running server only after Claude Code restarts it;
  until then, test by calling the index functions from Python.
