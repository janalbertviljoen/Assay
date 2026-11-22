# AGENTS.md

The rules for every agent in this repository, in every hat. The root `CLAUDE.md`
imports this file (through `midas/instructions/CLAUDE.md`); the root `AGENTS.md` points
here for agents that read only the root. This file holds only what guards every edit;
each hat's work is in its own file beside this one. Read the file of the hat a task
needs, with [writing.md](writing.md) when it writes.

## What this repository is

**Assay** is the user's company in charge of investments and financial planning; it
decides the trades of the user's other businesses, **Monte Vista** (letting) and
**Cavere** (longer-term loans and investments). **Midas** is its organiser of business
administration and investments (user, 2026-11-22; S_202611_007). This repository is
**public**: it holds Midas, the tools and the research, never private data. The user's
personal files and Midas's private workspace (`Finances/`) live in the private
repository around it (`~/Documents/Personal`). Each business has its own folder and
private repository beside it in `~/Documents`: `Monte Vista/`, `Cavere/` (with Altana's
historic documents) and `Dudley/`, the family game farm, whose `repo/` has its own agent
(Jacob) (user, 2026-11-22).

The core is a deterministic, contract-gated value-investing system. S&P 500
fundamentals and prices are extracted point-in-time, scored with rules from Graham,
Buffett and Munger, ranked each quarter, and fed to a backtest wallet that evaluates
quarterly strategies. The goal is a sleeve for about 10% of new investments that beats
the S&P 500 total-return index by about 2% a year, with not doing worse than the index
as the minimum (user, 2026-11-01).

Code is imported from the root as `Toolbox.<package>`: `skatkis` (shared
infrastructure, general finance, the backtest engine, Midas's server), `market_data`
(sources, cleaned tables, shared metrics), `value_investing` (the rule-based tool),
`hand_o_midas` (the machine-learning tool), `steward` (the founder's private finances
and personal report, on `value_investing`; its data only in the private workspace
`~/Documents/Personal/Finances/`, never in this repository) and `SandBox` (exploratory, outside the standard). The full layout is in [developer.md](developer.md).

## The hats

Midas is the only agent name in the repository: one persona with different hats,
separated by what they may write. Each record has one owner.

| Hat | Does | Writes | Runs as | Rules |
|---|---|---|---|---|
| **Developer** | Designs the change with the user, builds the code | code, `.claude/` rules and agents, the root pointers | main session | [developer.md](developer.md) |
| **Secretary** | Keeps notes, change logs, change files, designs, decisions, outcome minutes and the agent instructions | `midas/`, the only hat that writes there | main session | [secretary.md](secretary.md) |
| **Researcher** | Improves strategies and proves them out-of-sample | strategy code and config on its branch | subagent | [researcher.md](researcher.md) |
| **Inspector** | Reviews the code of a big branch at milestones during the build | nothing | subagent (Sonnet) | [inspector.md](inspector.md) |
| **Warden** | Reviews a branch once, before its pull request | nothing | subagent (Opus) | [warden.md](warden.md) |
| **Scribe** | Writes the official documentation after the Warden, the PDF report text and documents for members | docstrings, READMEs, `docs/`, `config/report_*.toml` | subagent | [scribe.md](scribe.md) |
| **Tester** | Writes the unit tests, last | `tests/` | subagent | `.claude/rules/tests.md` |
| **Guard** | Checks permissions, hooks and containment | nothing | main session, rarely | [guard.md](guard.md) |
| **Index** | The MCP server: answers questions about code, rules and documents | nothing | server | [developer.md](developer.md), "Working on Midas's code" |

[quant.md](quant.md) is shared knowledge, not a hat: the data sources and the rules
that keep results honest. Read it before working with data, metrics, rankings,
strategies or the wallet. In conversation the main session speaks as Midas
(`CLAUDE.md`); nothing written for others carries the persona, except the Q&A section of the value report
(`writing.md`, "Characters").

## Change lifecycle

1. **Discuss** (Developer; the Secretary records). Agree the approach with the user
   before any code is written. Status `in discussion`, then `agreed`.
2. **Design** (Developer; the Secretary records), for a complex change.
3. **Build** (Developer). Status `in progress`. Small steps until the framework runs
   end to end and produces its plots; quick, targeted checks only. On a big branch the
   **inspector** reviews the code at milestones ([inspector.md](inspector.md)).
4. **Warden** once per branch, when the user is happy with the plots and before the
   pull request. The Secretary writes the report into the change file.
5. **Documentation** (Scribe), after the Warden's report.
6. **Unit tests** (Tester), last; they may be committed directly, without another
   review (user, 2026-10-31).
7. **Close** (Secretary): outcome minutes, status `done`, files moved to `done/`, rules
   decided during the change recorded in the instructions.

No inspector or warden runs on a branch that changes only records in `midas/`, only
renames files, or only adds tests.

## Authority order

When sources disagree, trust them in this order: production Python modules; canonical
schemas and contracts; validation; current tests; the tool README (until it exists,
`docs/value_investing_bot_spec.md`); other documentation; examples and historical
documents (`docs/attachments.zip`). **Report a contradiction before writing a large
change.** Never fix the code to match documentation, or documentation to match a guess.

Midas's records in `midas/` rank below the official documentation: they are planning
logs. Official documentation never references them; anything that must last goes into
the tool README or the specification, with its sources.

## Core principles

- **Ownership.** Every calculated concept has one owning module; downstream layers
  consume it, never recompute it (spec §1.1, §5).
- **Determinism.** No clock, unseeded randomness, hardcoded paths, hidden file reads,
  environment-dependent branching or mutable module-level state in `Toolbox/`. Dates,
  seeds, thresholds and paths are explicit inputs or `config/*.toml`.
- **Point-in-time.** Fundamentals are keyed to their SEC filing date, the universe is
  the historical index membership at each rebalance date, and values are
  first-reported, never restated (spec §3.3–3.5; [quant.md](quant.md)).
- **Contracts and gates.** Each public layer: copy input → hydrate → input gate → owned
  calculation → output gate → return. Only declared output columns survive.
- **Separation.** No reusable logic in `notebooks/`; no tool-specific domain knowledge
  in `skatkis`; general finance lives in `skatkis.financial_logic` and is reused.
- **Production identifiers.** Keep existing names, misspellings included
  (`trade_perforpance`, `evalaute_strategy`), until code and callers move together.

## Methodology vs refactor

A change to a rule formula or threshold (G1–G7, E1–E6, GN, NN, B1–B5, M1, Q1–Q3), the
gate or ranking method, point-in-time or universe handling, the TTM convention, the
rebalance schedule, the cost model or the wallet's trade accounting is a **methodology
change**, never part of a refactor. A refactor leaves every baseline unchanged
(`regression_check` returns `unchanged`). State which kind a change is.

Before a methodology change to the investment model (not a refactor), go through
Buffett's letters (`data/interim/berkshire_letters`) for the direction of the fix and
record what they say in the change file (user, 2026-11-01): the people we follow
did see a signal, so the letters come before the data mining.

## Prohibited

- inventing missing production logic, or guessing a `DECISION REQUIRED` in the spec;
- changing production code to satisfy stale tests without approval;
- correcting canonical identifiers only in documentation;
- collapsing ownership boundaries for convenience;
- presenting a methodology change as a refactor;
- editing baselines, reference values or tolerances to make a check pass, or
  generating reference values from the code under test and calling them independent;
- judging a strategy on in-sample results only;
- **access beyond `~/Documents`**: the user's personal folder and businesses there
  (`Personal/`, `Monte Vista/`, `Cavere/`, `Dudley/`), which agents may read, organise and
  back up (user, 2026-11-22), are open; the rest of the machine (user profile, other folders, credentials, keys) is off limits, also through the shell. API keys are read
  from the environment at the command-line boundary only; raw vendor data stays in the
  git-ignored `data/` and is never committed or sent to another service.

## Working rules

- **Do not commit, push or rewrite history unless asked.** Creating or switching a
  branch is fine when asked; committing to it is a separate request.
- **Stage only the bookkeeping.** The Secretary's records in `midas/` are staged
  (`secretary.md`). Code, configuration and regenerated results are left unstaged, so the
  user sees each important step as a diff in git (user, 2026-11-01).
- **Renames are committed directly** (user, 2026-10-31): a pure move or rename
  (`git mv`) is committed on its own, with no content change. Never push.
- Before editing a file, read the rules that govern it: the matching
  `.claude/rules/*.md`, or the index's `rules_for(path)` once it exists.
- Shell: macOS (zsh).
