# S_202611_004: Beta access, design of the template and the submission

The target structure of the "Assay user" template and of the strategy submission.
Decisions and history are in the [change file](../changes/S_202611_004-beta-access.md).

## The template

Built in Assay as `templates/assay-user/`; published as a GitHub template repository at
each release.

```
assay-user/
├── README.md            three steps; works with no AI assistant
├── setup.sh             creates .venv, installs the pinned engine, writes .env
├── requirements.txt     assay @ git+https://github.com/janalbertviljoen/Assay.git@<tag>
├── .env                 the tester's own keys; git-ignored; created by setup.sh
├── benchmark/           managed by Assay, replaced on upgrade: the value_investing
│                        rules and index settings
├── strategies/          the tester's; one folder per strategy
├── data/                git-ignored; filled by one command
├── results/             the tester's plots and reports
├── notes/               the tester's own notes
├── log/                 the development log, with serial IDs; the report is compiled from it
├── AGENTS.md            starter rules of coding, written for testers; theirs to rewrite
├── assistant.md         the personal assistant hat, tool-neutral
├── CLAUDE.md            one line importing AGENTS.md, for those who use Claude Code
├── .vscode/             interpreter; MCP link for the editor's assistant
└── .mcp.json            the read-only Assay link, for Claude Code
```

- The template works with no AI assistant. `AGENTS.md` is the tool-neutral file; the
  files for one assistant are pointers to it.
- `setup.sh` writes `.env` with the SEC contact address (the only key SEC needs) and,
  if the tester has one, a FRED key (optional; the code works without it).
- The hat keeps the development log in `log/`, as the Secretary does for Midas: one entry
  per change with a serial ID, what changed, why and what it gave. A command issues the
  next ID and compiles the report, so a tester with no assistant keeps the log by hand.
- The hat writes only in `strategies/`, `notes/` and `log/`, never in `benchmark/` or the
  installed engine, and does not carry Midas's private rules.

## The submission

A tester sends a strategy folder; Assay receives it and returns a grade. The folder holds
the investing rules that lead to the picks, the minimum needed to pin the strategy down
and derive its picks independently, so that other members can use it too, plus the
development report compiled from the log. Assay derives the flags itself and never runs
the tester's code.

1. **Layout check.** The folder follows the layout and the rule file the schema declares.
   The same check ships in the package so a tester can run it before sending.
2. **Derive.** Assay runs the rules on its own data and point-in-time universe; the flags
   are its own.
3. **Backtest.** The wallet applies costs and trade accounting; the result is compared
   with the benchmark and with random picks under the same universe, dates and costs.
4. **Grade.** No signal, signal or good signal; no signal when the result is the same as
   random picks. The thresholds belong to `midas/accreditation.md` and are decided there.
5. **Accredit.** A strategy that passes the accreditation tests is stored in Assay and
   offered to the studio members; nothing else is stored.

Extra features a tester wishes to keep private may stay out of the folder, but then the
picks cannot be derived independently: such a submission can be graded as a private signal
check, never accredited or shared (to be confirmed).
