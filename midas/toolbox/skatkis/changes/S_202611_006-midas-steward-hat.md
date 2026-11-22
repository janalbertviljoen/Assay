# S_202611_006: Midas, the steward hat, keeper of the founder's private finances

| Field | Value |
|---|---|
| Status | in progress |
| Priority | high |
| Kind | new capability |
| Depends on | none |
| Branch | `feature/value-investing/vi-202611-003-personal-buy-list` (shared with VI_202611_003: the steward reuses its buy list and grew out of it in the same session) |
| Raised | 2026-11-19 |

## Description

The user wants a hat that keeps all of their private finances and reasons about them
in Charlie Munger's manner: the accounts, holdings and their cost, the tax-free account's
room, the capital-gains exclusion used each tax year, the retirement fund, contribution
plans, and the budget. Today these live only in statements and in the chat, so every
session starts over. The investor hat (S_202611_002) is member-facing and never gives a
personal allocation; this hat is private, for the founder alone.

## Agreed approach

- **A Midas hat, not a second persona.** "Midas is the only agent name in the
  repository" (`AGENTS.md`) and Midas "never speaks as a real investor" (S_202611_002)
  both stand. The hat works by Munger's published principles (inversion, avoiding
  stupidity before seeking brilliance, a checklist, the circle of competence) and quotes
  him with attribution, never speaking as him.
- **Private data only in `data/private/steward/`** (git-ignored): a ledger of accounts,
  holdings with cost, tax-free account room (yearly and lifetime), the capital-gains
  exclusion used per tax year, the retirement fund, contribution plans, the satellite
  sleeve, and the budget (income, expenses, business and property figures the user gives
  it). Other people's details are never kept.
- **The committed files hold the role, never a figure**: the hat's rules file in
  `midas/instructions/` and its agent definition in `.claude/agents/`.
- **Never shared:** not served to Assay members, not in any report, not indexed by the
  Midas index (S_202610_002 must exclude `data/private/`), not in agent memory.
- **Updated from what the user gives it**: statements and screenshots. EasyEquities has
  no client API; its AI Tools terms (March 2026) restrict the use of its AI output, and
  the unofficial clients need the login password, so no automated feed.

## Planned

- 2026-11-22 (user): once the founder holds the picks, track the number of shares held now
  and then (from statements or screenshots, in the private input) and value them at the
  latest S&P 500 closes of the price update, so the net worth follows the picks.

## Open decisions (user)

- The hat's name: "the Steward" is the working name; the user calls it Munger.

## Decisions

- 2026-11-19 (user): a Midas hat that follows Munger's method, not a character named
  Munger.
- 2026-11-19 (user): it keeps investments and the budget, in `data/private/` only.
- 2026-11-19 (user): the hat is the founder's own. The founder directs the strategy; the
  hat advises and above all warns (Munger's inversion: how could this fail?), and is
  tuned to a higher appetite for risk than the investor hat's member-facing caution. It
  states each risk plainly and once, then respects the founder's decision.
- 2026-11-19 (user): the founder's property company is in scope: its books (the yearly
  workbook in `data/private/`), and its strategy of repaying the bond quickly, then
  refinancing to buy a second property, and investing through the company once its cash
  flow allows.

- 2026-11-19 (user): a personal report of about five pages: a summary of the whole
  portfolio, the property company's cash flow and projected value, bond and equity, and
  the value picks with the buy list and the price charts. It is written only to
  `data/private/steward/reports/` (git-ignored), never to the tracked `results/`; this
  narrows "never in any report" to "never in a tracked or shared report".
- 2026-11-19 (user): the code is a new tool package, `Toolbox/steward/`, reading a
  structured private input (`data/private/steward/finances.toml`) and reusing the value
  tool's picks and buy list; bond amortisation goes to `skatkis.financial_logic`.
- 2026-11-19 (user): the property projection shows the user's assumption (10% a year)
  beside a cautious 6%, over 5 and 20 years.

- 2026-11-22 (user, after the Warden's B1): the personal report's text is private too: it
  moves from `config/report_steward.toml` to `data/private/steward/report_text.toml`
  (git-ignored), and the tracked file is removed from the branch's history before the push.

## Notes

- 2026-11-19: the ledger was started in `data/private/steward/ledger.md` from the
  statements and screenshots of 2026-11-19, so the figures discussed that day are not
  lost.

- 2026-11-19: built `Toolbox/steward/` (`finances`, `projection`, `plots`, `report`,
  `__main__`), `skatkis.financial_logic.amortise`, `value_investing.buying` (the buying
  steps without IO, shared by the value tool's `buy` command and the steward) and
  `config/report_steward.toml` (placeholders only). `python -m Toolbox.steward report
  --as-of 2026-11-19` writes a five-page `personal_report.pdf` under
  `data/private/steward/reports/2026-11-19/`. The private input is
  `data/private/steward/finances.toml`. Not yet done: the hat's rules file and agent
  definition, the Inspector and Warden, the Scribe and the Tester.

- 2026-11-20 (user): the report projects every part to retirement (a `[person]` and a
  `[tfsa]` section in the private input): listed funds at an assumed total return with
  the TFSA contributions, the provident fund with contributions rising with salary, the
  property per scenario, the car left out, and the total also in today's money; the
  figure's axis is the founder's age.

- 2026-11-20 (user): promotions modelled as one-off raises of the contributions
  (`raises`); once the bond is repaid the property company reinvests all its profit in
  shares (`[property.after_bond]`: rent, costs, their growth, the company tax after the
  assessed loss), shown as its own row at retirement. The founder's personal rental
  income is left out for now.

- 2026-11-20 (user): the company's assessed loss is carried month by month from today:
  while the bond runs the taxable result is the rent paid (`rent_paid`) less the month's
  interest, levies and rates, about nil, so the loss lasts well beyond the bond.

- 2026-11-22 (user): risk phases by age (`[[person.phases]]`: 10% until 55, 8% until
  60, 7% until 65) for the listed funds and the company's share portfolio (`phased`);
  the provident fund keeps its own rate. The founder's glide path replaces the member
  glide path of S_202611_002 for the private projection only.

## Warden report

Reviewed together with VI_202611_003 on 2026-11-22 (commit fffc8d6); the report is in
[VI_202611_003](../../value_investing/changes/VI_202611_003-personal-buy-list.md).

## Kickoff prompt

Pick up S_202611_006. Settle the open decisions, then write the hat's rules file and agent
definition, and give the ledger a fixed layout the hat keeps up to date.

## Done when

- The hat's rules file and agent definition exist, hold no figures, and point to the
  ledger; the ledger has a fixed layout; the index excludes `data/private/`.
