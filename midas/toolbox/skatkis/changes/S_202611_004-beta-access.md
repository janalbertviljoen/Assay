# S_202611_004: Beta access: a read-only Midas chatbot and a workspace for VS Code testers

| Field | Value |
|---|---|
| Status | in discussion |
| Priority | high |
| Kind | new capability |
| Depends on | S_202610_002 (index server) |
| Branch | `feature/skatkis/s-202611-004-mcp-member-access` |
| Raised | 2026-11-07 |

## Description

The beta moves from the founder alone to trusted people and testers. Today the MCP
server is a local process that Claude Code starts, so nobody else can reach it. The
beta needs two ways in: a link that lets a tester ask Midas about the report without
touching code, and a workspace for testers who work in VS Code. Neither may expose the
repository's working rules, and neither may cost money to run while the beta is small.
It supersedes the Codespaces plan in `assay/open_decisions.md`, "Beta workspace".

## Approach

Two tracks, built separately.

**A. Read-only chatbot (the link).** A hosted, read-only MCP server on a free platform.
It answers questions about the report and the published rules, serves excerpts and never
a whole file, writes nothing and runs no backtests. The `member` profile of `midas.md` §3
is built for it. A cold start of about 60 seconds is acceptable (user, 2026-11-07).
Whether a free Claude account can add a custom connector, and which free host to use,
are still to be checked.

**B. Workspace for VS Code testers.** A separate "Assay user" repository per tester,
holding their strategy settings and notes, with Midas installed as a pinned package.
They download their own data with one command into a directory they name, using their
own personal API keys. They see their own files in VS Code.

**Accreditation by submission.** A tester who has a strategy to accredit adds only its
settings file to the Assay repository through a pull request. The engine re-runs it on
our data with our hold-out. Only an accredited strategy is stored in Assay, so no space
is paid for strategies that do not earn (user, 2026-11-07).

**Access control.** Where a hosted server needs it, a file in the repository lists the
hash of each tester's access key with the tester's email as a label. A key is generated
by us, never chosen by the tester. Revoking is deleting the line and pushing.

## Open decisions (user)

- Where the engine runs for track B: Midas's recommendation is the package route (the
  engine installed as a pinned dependency, the instructions, SOP and records staying
  private); the alternative, a hosted-only engine, needs data we may not redistribute.
  To confirm with the user.
- The rule language of a submission: the existing rules (G1 to G7 and the others) with
  the tester's thresholds and weights is expressible today; a new factor must be written
  against the standard metrics columns. How far the language reaches is Midas's open
  question, and it sets how many strategies can be accredited.
- Midas's proposals, for decision: the grade is the strategy's result against a band of
  random-pick wallets (the company draws the calibration engine already makes), with the
  thresholds fixed in `midas/accreditation.md` before any strategy is graded; flags-only
  submissions are graded privately and never accredited; the log's serial ID is
  `<initials>_YYYYMM_NNN`, issued by a command.
- How a tester's own rules are kept apart from ours.
- Free host for track A, and whether free Claude accepts a custom connector.
- Whether the hosted server needs access keys at all for track A.

## Decisions

- 2026-11-07 (user): free hosting only, not the founder's machine; a cold start of
  about 60 seconds is acceptable.
- 2026-11-07 (user): access control is revocable and kept in a file in the repository.
  Midas's addition: hashes only, never plaintext.
- 2026-11-07 (user): testers use the shared API infrastructure with their own personal
  keys, and must not have to code the data download.
- 2026-11-07 (user): some testers only probe Midas, read-only; others work in VS Code.
- 2026-11-07 (user): a strategy is stored in Assay only after it is accredited.
- 2026-11-07 (user): `Trading_Bot` is renamed Assay and becomes the main repository.
  The founder renames it on GitHub; the repository's references follow (the remote URL
  and the name in `Toolbox/skatkis/midas/server.py`).
- 2026-11-07 (user): a template repository, "Assay user", branches from Assay. VS Code
  testers start from it with the directory layout and local environment already set to
  standard. It carries no copy of Midas's rules or records: a tester has their own
  instructions and can write their own rules of coding. It starts from a benchmark
  that the tester may personalise locally.
- 2026-11-07 (user): the experience should be as if the tester worked in the main
  repository, but siloed on their own resources. When Midas writes code for a tester it
  wears a personal assistant hat, new to this change and for the template repository
  only.
- 2026-11-07 (user): the starter benchmark is kept easy, and the `value_investing`
  strategy is included for everyone with access to the studio setup. Every accredited
  strategy will be shared the same way; this is the first.
- 2026-11-07 (user): the template is built in `templates/assay-user/` for now
  ([design](../design/S_202611_004-beta-access.md)). `benchmark/` (ours) and
  `strategies/` (theirs) are kept apart.
- 2026-11-07 (user): a tester sends the strategy folder, not a pull request. Assay
  receives it by a protocol that checks the folder layout and the backtesting rigour:
  an independent analysis. The strategy contains only buy and sell flags; Assay runs
  them through the wallet and gives a verdict. (Superseded by the next decision.)
- 2026-11-07 (user): the submission is the investing rules that lead to the flags, the
  minimum needed to pin the strategy down and derive its picks independently, so other
  members can use it. Assay derives the flags itself, backtests them and grades the
  result: no signal, signal or good signal, with no signal meaning the same as random
  picks. Only a strategy that passes the backtest accreditation is stored. Testers who
  keep a secret sauce may leave extras out, but the minimum must be there.
- 2026-11-07 (user): the personal assistant keeps the development log like the Secretary
  does, with serial IDs; a report compiled from it is sent with the folder.
- 2026-11-07 (user): not every tester has Claude. The template works with no AI
  assistant; `AGENTS.md` is the neutral file and Claude-specific files only point to it.
- 2026-11-07 (user): `setup.sh` writes the keys into the tester's own `.env`. Midas's
  note: SEC needs only a contact address and FRED's key is optional, so no tester has to
  create an account to start.
- 2026-11-07 (user): the rules we use to build the repository, the SOP and the
  instructions stay private; Midas may answer questions about them but never serves a
  whole file.

## Notes

- 2026-11-07: branch created from `main` after the merge of PR #11.
- 2026-11-07: the founder renamed the GitHub repository to Assay; `origin` now points at
  it and the server description names Assay.

- 2026-11-07: package built (`pyproject.toml`: setuptools backend, distribution `assay`,
  import name `Toolbox`, runtime dependencies, `mcp` extra). A wheel built from the
  branch imports `value_investing`, `market_data` and the wallet from outside the
  repository. Config and data paths are command-line arguments relative to the working
  directory, so the template holds its own `config/` and `data/`. Install line for the
  template: `assay @ git+https://github.com/janalbertviljoen/Assay.git@<tag>`, with a tag
  per release (to be made by the user after merging).
- 2026-11-07: finding: the server's lab tools still run only the BTC VWAP harness
  (`Toolbox/SandBox`), so the MCP does not yet expose `value_investing`; the `member`
  profile and the report tools are part of this change. The runtime dependencies repeat
  the `core` group in `pyproject.toml`; a dependency group cannot be read from the
  project table, so the two lists must be kept in step.

## Kickoff prompt

Pick up S_202611_004: read this file, `assay/notes.md` ("Members bring their own
Claude") and `assay/open_decisions.md` ("Beta workspace"), then settle the open
decisions with the user before any code.

## Done when

- A tester can add a link to their Claude and ask Midas about the report, read-only.
- A VS Code tester can set up a workspace, fetch their own data with one command and
  run their settings against the engine.
- An accredited strategy can be submitted as a settings file and re-run by the engine.
- Access can be revoked by one commit.
