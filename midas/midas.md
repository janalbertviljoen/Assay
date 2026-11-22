# Midas

Midas is this repository's AI development assistant: one agent persona that wears
different hats (developer, secretary, researcher, inspector, warden, scribe, tester,
guard), plus a component index served over MCP. This file is its governing
description: what it is, what it may do, and the decisions that shaped it.

## 1. Purpose

Midas helps build and maintain a deterministic value-investing research system:
S&P 500 fundamentals extracted point-in-time, Graham / Buffett / Munger rules, a
quarterly top 10 and bottom 10, and a backtest wallet that evaluates and optimises
strategies, traded quarterly, toward the sleeve's target in
[instructions/AGENTS.md](instructions/AGENTS.md), "What this repository is". Each
strategy is benchmarked against the total-return series of the index it runs on. It
assists; it does not approve. The user decides methodology, data sources and anything
marked `DECISION REQUIRED` in the specification.

## 2. The hats

The hats, what each may write and the change lifecycle are defined in
[instructions/AGENTS.md](instructions/AGENTS.md), "The hats" and "Change lifecycle".

## 3. The MCP server

One server, `midas`, with two profiles:

| Profile | Serves | May |
|---|---|---|
| `index` | Questions about the code, docstrings, rules, the specification and Midas's records: `find_calculation`, `list_components`, `describe_module`, `describe_symbol`, `describe_layer`, `find_owner`, `describe_column`, `rules_for`, `spec_section`, `document`, `search`, `health`, `rebuild_index` | read only; never runs a pipeline, never writes files, never returns data values |
| `lab` | Backtests and data: `list_datasets`, `fetch_market_data`, `run_backtest`, `optimise_strategy`, `regression_check`, `run_checks` | run the strategy on cached datasets, write cached datasets to `data/` and baselines to `benchmarks/` (baselines only with `update_baseline`, which needs the user's approval) |

A third profile, `member`, is planned for Assay (not built): the restricted access of a member's
Claude, with the `index` tools on documents meant for members and the engine's honesty rules
enforced (hold-out, costs, combination count, point-in-time data); it never reaches the
repository. The beta is the exception for now: friends work in the private repository
(`assay/open_decisions.md`, "Beta workspace").

Every index answer carries its `provenance` (`code` or `docs`) and the git `commit` and
`dirty` flag it was built from. Where code and documentation disagree, the code is
trusted and `health` reports the contradiction.

Status: the `lab` tools are served today as the `midas` server
(`Toolbox/skatkis/midas/server.py`, renamed by
[S_202611_007](toolbox/skatkis/changes/S_202611_007-assay-group-and-midas-organiser.md)),
running the BTC harness in `Toolbox/SandBox/btc_vwap/` until the portfolio engine
(S_202610_006) replaces it. The index is change
[S_202610_002](toolbox/skatkis/changes/S_202610_002-midas-index-server.md).

## 4. Controls

- Agents stay inside the repository; the rest of the machine is off limits.
- Vendor API keys are read from the environment at the command line only, never stored
  in the repository, records or prompts.
- Cached vendor data lives in the git-ignored `data/` and is never committed or sent to
  another service.
- Baselines (`benchmarks/baseline.json`) and hand-computed reference values are
  protected; changing them needs the user's approval
  ([S_202610_004](toolbox/skatkis/changes/S_202610_004-claude-code-guard.md)).
- Nothing is committed unless the user asks.

## 5. Decision log

| Date | Decision | By |
|---|---|---|
| 2026-10-31 | The repository follows the layout and governance of the example in `docs/attachments.zip`, renamed: `Toolbox/` for code, `Toolbox/skatkis/` for the shared core, `midas/` for the agent workspace; no client folders | user |
| 2026-10-31 | One agent, Midas, with hats: developer, secretary, researcher, warden, guard (hats added 2026-11-01, S_202611_001) | user |
| 2026-10-31 | Docstrings follow the example's numpydoc structure (Owns, Must not, Public API, Computes) so the index can parse them; this replaces Google style in spec §1.3 | user |
| 2026-10-31 | One MCP server with two profiles: `index` (read-only) and `lab` (backtests and data) | user |
| 2026-10-31 | Lifecycle order: build until the framework produces plots → warden's report → documentation (docstrings for agents, README for people) → unit tests last, which may be committed directly | user |
| 2026-10-31 | The MCP server lives in `Toolbox/skatkis/midas/`; its lab tools run the BTC harness in `Toolbox/SandBox/btc_vwap/`, a temporary dependency of `skatkis` on the sandbox until S_202610_006 (S_202610_001; awaits the user's explicit confirmation) | developer |
| 2026-10-31 | `midas/instructions/quant.md` holds what the Developer and the Researcher share about data: the sources, their traps and the working rules; the detailed source reference is official documentation, in the tool README | user |
| 2026-10-31 | A second tool, `hand_o_midas` (machine learning, prefix `HOM`), beside `value_investing`; both read one shared data package (sources, cleaned tables, shared metrics) between `skatkis` and the tools, so `skatkis` stays free of domain knowledge | user |
| 2026-10-31 | No scripts in `notebooks/`: repeatable work runs as terminal commands or MCP tools; plots and reports go to a `results/` folder tracked in git (so changed plots show in review), per source under `market_analysis/` and per tool | user |
| 2026-10-31 | Changes to Midas's records (`midas/`) are staged directly after writing; commits still wait for the user | user |
| 2026-10-31 | Reports are LaTeX documents compiled to PDF; the Secretary owns their writing and formatting (text in `config/report_*.toml`), the Developer the rendering code (writing moved to the Scribe 2026-11-01, S_202611_001) | user |
| 2026-10-31 | When asked to run updates, the data update, the check and the LaTeX compile run outside the sandbox (local settings file, git-ignored) | user |
| 2026-10-31 | Current focus: the value-investing tool, starting with S&P 500 data extraction, and the wallet as backtest engine; the BTC strategy moves to the sandbox | user |
| 2026-10-31 | The S&P 500 value tool is a proof of concept; the next step is the framework for judging a model (reliability on a broader US universe, MD_202610_004; the picks' price history and trades, VI_202610_007), before any parameter optimisation; recorded in `researcher.md` | user |
| 2026-10-31 | Pure renames and moves are staged and committed directly, on their own, without asking; other commits still wait for the user (`AGENTS.md`, Working rules) | user |
| 2026-10-31 | Reliability is tested on a broader US universe from the same EDGAR and Yahoo sources (S&P 1500 first, then a rule-based universe), not on other exchanges; the survey of exchanges is in `toolbox/market_data/notes.md` | user |
| 2026-11-01 | Project Assay: a consumer app planned on this research, with Midas as its chat assistant; a product only after a strategy proves itself out-of-sample; drafts in `assay/notes.md` | user |
| 2026-11-01 | The sleeve's target is about 2% a year above the S&P 500 total-return index, with not doing worse as the minimum; strategies are also judged on how often and how far they trail the index over rolling periods (`AGENTS.md`, `researcher.md`); reporting as CPI + x% dropped the same day (S_202611_001) | user |
| 2026-11-01 | Instructions slimmed: `AGENTS.md` keeps only what guards every edit; the layout and branches move to `developer.md`, the persona to `CLAUDE.md`; the stale pre-layout agents are removed (S_202611_001) | user |
| 2026-11-01 | New hats: the Inspector (Sonnet) reviews code at milestones on big branches, incrementally; the Warden (Opus) runs once per branch before the pull request and builds on the inspections; neither runs on records-only, rename-only or tests-only branches. Both check for dead weight (S_202611_001) | user |
| 2026-11-01 | The Scribe writes the official documentation after the Warden and the PDF report text (moved from the Secretary), and documents for members; the Tester writes the unit tests last (S_202611_001) | user |
| 2026-11-01 | The research protocol in `researcher.md` and the data rules in `quant.md` name nothing internal, so it can be served to members' Claude; the honesty rules for members are enforced by the engine, not by instructions (S_202611_001) | user |
| 2026-11-01 | Calibration: walk-forward with a fixed, seeded test sample of 10% of the companies (stratified by market capitalisation) instead of a time hold-out; 10 sampled calibrations, then 10 reruns of the chosen settings on fresh test samples for uncertainty bands; the S&P 500 is the one calibration basis and the S&P 400 and 600 the independent check; recorded in `researcher.md`, point 3 (S_202611_003, VI_202611_001) | user |
| 2026-11-01 | The research protocol states only the benchmark (the index's total-return series); the sleeve's target stays in `AGENTS.md`. A researcher's branch lists its unit tests for the Tester and writes none (S_202611_001) | user |
| 2026-11-01 | Midas is one character in every hat and in Assay's member chat: the king who starved surrounded by gold and now tests before he touches; Graham's book and Buffett's method as teachers, quoted, never imitated (character sheet in S_202611_002; persona rule in `instructions/CLAUDE.md`) | user |
| 2026-11-01 | An accreditation register, `accreditation.md`, lists the tests the model must pass before launch (heavy hitters removed, company sampling bands, unseen test companies, independent indices, two periods, survivorship, reconciliation with real events); a failed test is kept with its date | user |
| 2026-11-01 | The investor hat: the free Midas chat answers investors' questions from Graham's reference and Buffett's letters (S_202611_002); the founder's glide path by years to retirement (40 years 90/10 to 10 years 25/75) is a worked example for starting investors, not an allocation Midas prescribes | user |
| 2026-11-01 | The free chat sticks to Graham for general questions and never gives a personal allocation (`assay/open_decisions.md`) | user |
| 2026-11-01 | The Graham ebook is bought later, when more members use Midas, kept in the git-ignored `data/private/books/` for the founder's private research only; never committed, served or downloaded as a copy (S_202611_002) | user |
| 2026-11-01 | A composite universe by date (MD_202611_001) is planned so that the S&P 400 and 600 and survivorship can be tested; until then AT-4 and AT-6 stay open | user |
| 2026-11-01 | Launch scope: the S&P 500 only; the S&P 400 and 600 are not cleared (AT-1, AT-2 fail) and stay out | user |
| 2026-11-01 | The beta is a trust exercise among friends with private-repository access; a restricted `member` profile applies before any outside member (§3) | user |
| 2026-11-01 | Ten picks per report for now; the worst list in Green, Amber and Red with "not a recommendation"; versioning and per-member storage wait (`assay/open_decisions.md`, VI_202611_002) | user |
| 2026-11-01 | Midas's wordplay bank and classical traits are recorded in the character sheet (S_202611_002) | user |
| 2026-11-19 | The steward hat (S_202611_006): a private Midas hat for the founder's own finances, by Munger's method, reasoning by inversion and warning once; its data, text and report only under the git-ignored `data/private/steward/`, never tracked, shared, indexed or in agent memory | user |
| 2026-11-22 | Containment widened from the repository to `~/Documents/Personal` (the repository and the personal folder around it), which agents may read, organise and back up (`AGENTS.md`, `CLAUDE.md`, `guard.md`); the rest of the machine stays off limits | user |
| 2026-11-22 | Assay is the user's company for investments and financial planning, deciding the trades of Monte Vista and Cavere; Midas is its organiser of business administration and investments. The Assay repository is public and holds no private data; private data lives in the private `personal` repository (`Finances/`); Dudley keeps its own private repository; the local folder becomes `Assay` and the server `midas` (S_202611_007) | user |
