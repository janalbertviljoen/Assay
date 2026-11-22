# S_202611_007: Assay as the group's company, Midas as its organiser

| Field | Value |
|---|---|
| Status | in progress |
| Priority | high |
| Kind | tooling |
| Depends on | S_202611_006 (the steward), S_202610_002 (the server's rename to `midas`) |
| Branch | `feature/midas/s-202611-007-assay-group` |
| Raised | 2026-11-22 |

## Description

The repository grew out of a trading bot, and its instructions, its local folder
(`Trading_Bot`) and its MCP server (`trading-bot`) still say so. The user's picture
(2026-11-22) is wider: **Assay** is the user's company in charge of investments and
financial planning; it decides the trades of the user's other businesses: **Monte
Vista** (short-term and long-term letting) and **Cavere** (longer-term loans and
investments). **Midas** becomes the organiser of the user's business administration and
investments across them. A separate private repository holds the user's personal and
business files; Midas reads and organises it to help with all the companies. A third,
private repository serves the **Dudley** family game farm, indexed by its own agent,
Jacob.

The Assay repository on GitHub is **public**. So it holds Midas, the tools and the
research, never private data: the private side lives in the private repository.

## Agreed approach

- **Three repositories, three audiences.**
  - `Assay` (public): Midas, the tools (`Toolbox/`), the research and the reports' code.
    No figures, documents or decisions of the user or the companies.
  - `personal` (private, `~/Documents/Personal`): personal and business files, including
    `Monte Vista/`, `Cavere Holdings/` and Midas's private workspace `Finances/` (the
    ledger, the finances input, the personal report's text, the reports and the account
    statements), backed up there.
  - `dudley` (private): the family game farm's records and the Jacob agent; Midas does not
    write there.
- **Midas's access to the private repository**: read, organise and back up (the user's
  rule of 2026-11-22 in `AGENTS.md`), never copying its content into the public `Assay`.
- **The steward reads and writes only in the private workspace** (`../Finances` from the
  repository root): its input, text and reports move out of `data/private/steward/`,
  where they were git-ignored but backed up nowhere.
- **Naming.** The local folder becomes `Assay`; `AGENTS.md` describes Assay and Midas's
  role; the MCP server is registered as `midas` (S_202610_002 planned the name) and the
  agents' tool names follow. Claude Code keeps its memory per folder path, so the notes
  are copied to the new path before the first session there.

## Decisions

- 2026-11-22 (user): private data in the private `personal` repository; Dudley stays
  private (as decided on 2026-11-22 for the Dudley design); the local folder is renamed
  `Assay`; Midas may read, organise and back up the private repository.

## Notes

- 2026-11-22: migration checked against the kickoff prompt. The folder is `Assay`, the
  server `midas` (`.mcp.json`), and the steward reads and writes `../Finances` (its
  default in `Toolbox/steward/__main__.py`). No private data is tracked or in the git
  history: the account numbers and names from the statements appear in no commit
  (`git log --all -S`), and `data/` is git-ignored. Leftovers cleared: the empty
  `Personal/Trading_Bot/` folder, its line in the private repository's `.gitignore`,
  the `trading-bot` status in `midas.md` and the `Toolbox/__init__.py` docstring. Old
  scratchpad paths in closed change files are historical and stay.

## Kickoff prompt

Pick up S_202611_007. Check that the private workspace `~/Documents/Personal/Finances/`
holds the steward's data and the steward reads it there, that the folder is named `Assay`
and the server `midas`, and that no private data remains in the public repository.

## Done when

- `AGENTS.md` describes Assay, its companies and Midas's role; the private data lives in
  the private repository and nowhere in the public one; the folder is `Assay` and the
  server `midas`.
