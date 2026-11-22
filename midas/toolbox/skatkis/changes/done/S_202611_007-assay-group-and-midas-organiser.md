# S_202611_007: Assay as the group's company, Midas as its organiser

| Field | Value |
|---|---|
| Status | done (2026-11-22) |
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

## Outcome

Done 2026-11-22. Assay is the user's company for investments and financial planning,
deciding the trades of Monte Vista and Cavere; Midas is its organiser. The public `Assay`
repository holds Midas, the tools and the research, and no private data. The private
side lives in the `personal` repository (`~/Documents/Personal`), with Midas's private
workspace `Finances/` (ledger, finances input, report text, reports, statements), where
the steward now reads and writes (`../Finances`, its default). Monte Vista, Cavere and
Dudley ended up in their own folders and private repositories beside it in
`~/Documents`, rather than inside `personal` as first agreed (user, 2026-11-22);
`AGENTS.md` says so. Midas may read, organise and back up those folders, never copying
their content into `Assay`.

The local folder was renamed from `Trading_Bot` to `Assay`, the MCP server from
`trading-bot` to `midas` (planned by S_202610_002, done here), and the Claude Code
memory copied to the new path. A check of tracked files and the whole git history found
no private data. Merged in pull request #14 (commits `6ad29ad`, `ea58a86`).

No Inspector or Warden ran: the user waived the Warden for this change on 2026-11-22,
the code changes being the steward's default path and the server's name.

## Kickoff prompt

Pick up S_202611_007. Check that the private workspace `~/Documents/Personal/Finances/`
holds the steward's data and the steward reads it there, that the folder is named `Assay`
and the server `midas`, and that no private data remains in the public repository.

## Done when

- `AGENTS.md` describes Assay, its companies and Midas's role; the private data lives in
  the private repository and nowhere in the public one; the folder is `Assay` and the
  server `midas`.
