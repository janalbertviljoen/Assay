# S_202611_008: Repositories side by side, Midas defined once

| Field | Value |
|---|---|
| Status | in progress |
| Priority | high |
| Kind | tooling |
| Depends on | S_202611_007 |
| Branch | `feature/skatkis/move-assay-to-documents` |
| Raised | 2026-11-22 |

## Description

Assay sat inside the private `Personal` repository, while the businesses sat beside it in
`~/Documents`. The user wants one agent in Personal for all their affairs, which turns to
Assay for investing and financial planning, and the same for each business. Copying
Midas's instructions into every repository would let them drift apart.

## Agreed approach

- **Every repository on one level** in `~/Documents`: `Assay/`, `Personal/`,
  `Monte Vista/`, `Cavere/`, `Dudley/`.
- **Midas is defined once, in Assay**: the character sheet, the hats, the tools and the
  `midas` server. Assay is public, and the member chat needs the persona there.
- **Thin agents elsewhere.** Personal, Monte Vista and Cavere each get a `CLAUDE.md`
  that imports the persona from `~/Documents/Assay` and adds only their own rules
  (Personal: `Finances/`, tax, documents), and an `assay` skill that does investing and
  financial planning in `../Assay` through the `midas` server.
- **Dudley keeps Jacob**, its own agent.
- **`steward` becomes `financial_planning`**: a general tool for any owner, run on
  Personal's `Finances/` today and on Monte Vista's or Cavere's books later. A refactor:
  no output changes.

## Decisions

- 2026-11-22 (user): Assay moves to `~/Documents/Assay`; the default for the private
  workspace becomes `../Personal/Finances`.
- 2026-11-22 (user): Midas is defined once, in Assay, with thin agents and an `assay`
  skill in Personal, Monte Vista and Cavere.
- 2026-11-22 (user): the package is named `financial_planning` (the name `midas` is taken
  by the server package `Toolbox/skatkis/midas`).

## Notes

- 2026-11-22: the default workspace path, the instructions and the decision log updated
  (`ad315dc`); the package renamed by a pure move (`06cd034`), then its references;
  Black, ruff and pyright clean, 467 tests pass.
- 2026-11-22 (user): the branch is merged into `main` before the change is finished, with
  no Warden, to close the reorganisation and backup of the user's files; the change stays
  `in progress` and the remaining steps go on a new branch.
- Still to do: the user moves the folder and copies Claude Code's memory; then the thin
  agents and the `assay` skill in Personal, Monte Vista and Cavere.

## Done when

- Assay runs from `~/Documents/Assay` with a rebuilt `.venv` and its memory carried over.
- A session started in Personal, Monte Vista or Cavere speaks as Midas and reaches the
  `midas` server and Assay's tools through the `assay` skill, with no instruction copied.
- No `steward` name is left in code or current instructions.
