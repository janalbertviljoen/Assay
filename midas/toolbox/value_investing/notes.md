# value_investing notes

## Planning (preliminary)

### Objective (2026-10-31, open → S_202610_006)

A trading bot, not a risk model. The user holds mostly the S&P 500 and wants about 10%
of new investments in a value-investing sleeve that beats the S&P 500 total-return
index by about 2% a year; not doing worse than the index is the minimum (user,
2026-11-01). Trades are quarterly, across S&P 500 companies; the wallet tracks
combinations of strategies, judged out-of-sample on excess return over the index and on
how often and how far they trail it over rolling periods. Reporting as CPI + x% was
dropped (user, 2026-11-01). The API matters because
backtesting and optimising the metrics needs point-in-time fundamentals over many years.

- Hypothesis (user, 2026-11-01): the sleeve leads the index more often than it trails
  it, and is safer in a correction of overvalued stocks (an AI bubble), because the
  rules exclude expensive stocks by design. To test: the same exclusion makes value
  trail during a bubble's run-up (1998–2000, 2019–2021), so the rolling comparison
  should show both phases.

### Open owner decisions from the spec (2026-10-31, open)

From `docs/value_investing_bot_spec.md` §9; each blocks the changes noted.

1. Data: paid vendor budget, or EDGAR only? Decided 2026-10-31: free sources (EDGAR,
   Wikipedia or `fja05680`, `yfinance`); survivorship gap accepted for now
   → MD_202610_001
2. Bottom ten: sell/avoid, or short? → S_202610_006
3. Financials and REITs: exclude, or separate scoring? Decided 2026-10-31: REITs and
   financial companies excluded; bonds are outside this tool
   → MD_202610_001, VI_202610_002, MD_202610_002
4. Wallet interface: signals, target weights or orders? → S_202610_006
5. Reporting currency: USD or ZAR? Decided 2026-10-31: main analysis in USD; ZAR
   secondary, once refined and to track the actual record (FRED `DEXSFUS`)
   → MD_202610_001
6. DAG engine: stdlib `graphlib` registry or Hamilton/Dagster? Decided 2026-10-31:
   `graphlib` → MD_202610_001

### The user's existing portfolio as a comparison (2026-10-31, open)

The user's current portfolio is a South African tax-free savings account (TFSA) of
JSE-listed ETFs and feeder funds, mostly US large-cap and technology (S&P 500, S&P 500
IT, Nasdaq 100, global indices); its statement benchmarks against the FTSE/JSE Top 40.
The statement is kept out of the repository, in the git-ignored `data/private/`.

- The account is a comparison only (user, 2026-10-31): the sleeve's results are tracked
  against these standard investments, in ZAR. It does not constrain where the sleeve is
  held.
- The weighting of the diversification matters more than the account (user,
  2026-10-31): the analysis should show how the sleeve shifts the overall weighting,
  for when the user moves money into individual firms reachable in the TFSA on the JSE.
  A JSE universe may follow as a later change.

### From buyability score to a quarterly selection (2026-10-31, → S_202611_003, VI_202611_001)

The user's plan after VI_202610_002, in order:

1. Look at the buyability score on a casual sample (ten best, ten worst) to establish
   the pattern.
2. At each quarterly update, select the most likely best buys for the next quarter
   from the most recent point-in-time score: one prediction per quarter.
3. Calibrate the portfolio parameters: diversification rules and the weight bought of
   each candidate.
4. Backtest the combinations of weighting specifications and keep the one with the best
   portfolio performance out-of-sample. The optimisation follows the pattern of the
   BTC VWAP work in `notebooks/optimise_strategies.ipynb` (high-frequency triggers
   there; one quarterly decision here). → S_202610_006

### Roadmap after closing the per-index branch (2026-11-01, open)

The user's order of work (2026-11-01):

1. **Close out** the branch `feature/value-investing/vi-202610-007-pick-price-history`
   (committed; the user pushes it and opens the pull request).
2. **Optimise Midas**: the agent set-up itself (instructions, index server S_202610_002,
   guard S_202610_004); scope to agree at the start.
3. **Unit tests**, high priority: VI_202610_009.
4. **Documentation**: the tool README and the spec departures, the `market_data` README
   and the skatkis reference (sections 4 of both warden reports); then VI_202610_002 to
   006 close.
5. **A first version (V1) of the pipeline**: what V1 contains is to agree; candidates are
   the two strategies (VI_202610_008), the survivorship experiment (S_202610_008) and
   the historical membership (MD_202610_002).

Open decisions carried over: the delisted-lot accounting (VI_202610_006, N2) and the
deferral of the DAG engine (spec §9.6).

### The process so far: from proof of concept to judging a model (2026-10-31, open)

The order followed so far, and the next stage the user set (2026-10-31):

1. **Data.** S&P 500 fundamentals from EDGAR (first-reported, keyed to the filing
   date), Yahoo prices and dividends, the membership from Wikipedia (MD_202610_001,
   MD_202610_002).
2. **Rules and score.** The Graham, Buffett and Munger rules scored and binned per
   company and date, weighted by pass rate and past success (VI_202610_002 to
   VI_202610_005).
3. **Proof of concept.** The value report (VI_202610_006): yearly picks bought and
   held, or sold when the score falls, against the S&P 500 and Berkshire Hathaway.
   The wallets beat the index, with the biases stated (today's members only,
   look-ahead in the tag choice), so the result is provisional.
4. **Next: the framework for judging a model**, before any parameter is tuned:
   - reliability on companies the model has not seen, from the same sources: the S&P
     400 and 600, then a rule-based US universe (MD_202610_004); other exchanges were
     surveyed and set aside (`midas/toolbox/market_data/notes.md`);
   - a look at what the model does: each pick's price with its buys and sales, and the
     USD traded (VI_202610_007). The first look showed the user picks they would not
     buy and losers held for years ("Picks with weak past returns", "The wallet keeps
     its losers" below).
5. **Later: optimisation** of the parameters (thresholds, weights, the sell rule),
   out-of-sample, as the researcher's workflow sets out (S_202610_006).

The rule behind step 4 is recorded in `midas/instructions/researcher.md` ("Judge the
model before tuning it").

### Follow-ups pencilled in after the warden's first run (2026-10-31, open)

Put off by the user as not urgent (2026-10-31); details in VI_202610_006, "Warden
report":

1. The tag-choice fix (point-in-time label choice): done 2026-11-01 (MD_202610_002);
   the two strict-xfail tests pass.
2. Historical S&P 500 members, to remove the survivorship bias (MD_202610_002).
3. JSE data and the Top 40 comparison: returns-only first, or a paid fundamentals
   source (MD_202610_003).
4. Whether the picks are available in the EasyEquities USD account (the user checks in
   the app).
5. The warden's should-fix items S3 to S9, S11 and S12: done 2026-11-01 (VI_202610_006,
   "Fixes after the report"); the follow-up run's findings are in VI_202610_007.
6. Documentation (tool README, spec departures, skatkis reference) and the unit tests
   the warden listed.
7. Report conventions the user set, to record as standing rules for the secretary:
   tables kept whole on one page where they fit, benchmarks thick and black (S&P 500
   dashed, Berkshire dash-dot), full company names in the concluding parts, a recent
   investor as the reference.

### Spec §1.3 docstring style (2026-10-31, → S_202610_003)

Spec §1.3 prescribes Google style; the user chose the numpydoc structure of
`.claude/rules/docstrings.md`. The spec is updated in S_202610_003. §1.4 also still
asks for `ruff format --check`, where the repository uses Black (warden, S_202611_001,
2026-11-01); a spec decision for the scribe.

## Open methodology questions

### EDGAR history is too short for the long Graham windows (2026-10-31, → VI_202610_002)

Found in the first live pull (MD_202610_001, Apple, Microsoft, Coca-Cola). XBRL
filings start in mid-2009; with comparative figures, values reach back to periods ending
in 2006–2007, but nothing was filed in XBRL before 2009. SEC's Financial Statement Data
Sets also start in 2009. So "20 years where EDGAR has it" gives about 17–20 years of
periods, and the rules with long windows first become computable late:

| Rule | Window | First rebalance with a full window (about) |
|---|---|---|
| G3 earnings stability, B1 ROE | 10 years | 2016–2017 |
| G5 earnings growth | 13 years | 2019–2020 |
| G4 dividend record | 20 years | 2026 or later |

A backtest with the full defensive rules would then cover only about 2017–2026, which
leaves little out-of-sample history. Options, for the user to decide:

- Dividend history (G4) from the price source instead: `yfinance` dividends go back
  decades, though not point-in-time filings.
- Shorter windows as explicit, configurable parameters: a methodology change, recorded
  as such.
- A paid source with point-in-time fundamentals before 2009.
- Rules phased in: each rule applies only from the first date its window is full.

Decided 2026-10-31, recorded in VI_202610_002: dividend history from the price source,
the windows as explicit parameters (Graham's and Buffett's values by default), and
rules phased in until their window is full. G4's phase-in was built on 2026-11-01.

User, 2026-11-01: G3 is to be reduced from 10 to 3 years for lack of data; 3 years
corresponds to the investment horizon. Not applied yet (→ VI_202611_001).

### Universe looks ahead: today's members scored in the past (2026-10-31, open)

Found in VI_202610_004. The buyability table scores today's S&P 500 members on every
past date, including companies that joined the index later because they grew (TSLA
added 2020-12-21, scored and shorted in January 2020). This flatters any long book and
punishes any short book: the equal-weighted wallet of every scored company beats
`^SP500TR` by +2.9% a year, and -0.4% once each date keeps only companies already added
(`date_added` from the constituents table). The filter fixes additions only; companies
removed from the index are still missing until the historical membership of
MD_202610_002 exists. A methodology change; to be approved by the user.

### The wallet keeps its losers (2026-10-31, open)

Seen in the first price-history figure (VI_202610_007). The investor who started in
2023 sold almost nothing in three years: two small trims of Intel (about 4 USD), while
Skyworks was bought six times in a row as its price fell from about 110 to 65 USD. The
sell rule looks only at the score (sell below a 0-to-1 score of 0.4), and a company
whose price falls while its fundamentals hold scores higher, not lower, so the rule
never fires on it. Whether a price-based exit, a holding limit or a cap on repeat
purchases helps is a hypothesis for the researcher, once the framework for judging a
model is in place (`researcher.md`, "Judge the model before tuning it"); the user
noted (2026-10-31) that the parameters can be optimised later.

### Picks with weak past returns: value traps (2026-10-31, open)

The user looked up the last five years of the 2026-10-30 picks (First Solar, Cognizant,
Snap-on, Skyworks, ResMed) and would not buy them. A cheap-on-fundamentals screen
favours companies whose price has fallen, and some fall for a reason (value traps).
A price-trend or momentum condition (for example: no pick whose 12-month return lags
the S&P 500 by more than a threshold) would address it, but it is a methodology
change: a new rule, to be tested as a hypothesis out-of-sample (the researcher, on
the broader universe of MD_202610_004), not set by looking at today's picks. The price
history in the report (VI_202610_007) shows the problem first.

### Rule weighting strategies (2026-11-01, open, priority low → VI_202611_001)

Gating belongs here too (user, 2026-11-01): the plain score stays; gates and weights are
later work. Gate designs 1 to 6 added nothing to the plain score on the S&P 500
(VI_202611_001, checks 7 to 9); G3 at 3 years passes 86% of companies, so it is hardly a gate.

Weights stay floored at 0 (user, 2026-11-01). To revisit, simple and complex: signed
weights, stability shrinkage, best-k by stability, weights by sector or regime, a
regression of excess return on the points. First look at signed weights (training
companies only, 3-month excess, 12 closed windows): no variant had a score correlation above 0.01,
because no single rule's mean rank correlation exceeds 0.02. Point curves per rule come
first, since a rank correlation misses a rule that rewards the middle of its range.

### Sell analysis at 2.5 years (2026-11-01, open, → VI_202611_001)

The strategy is buy and hold (Buffett; user, 2026-11-01), judged over 5 years. A 2.5-year
look at each pick would show whether to sell one that is crashing out earlier. A separate
analysis, after the buy side is settled: it needs a sell rule fixed beforehand and
tested out-of-sample like any other.

### The sell side uses another scale than the picks (2026-11-02, open → sell/short optimisation, VI_202611_001)

The picks rank on the raw weighted score (`score_binned_weighted`); the sell rule and the
report's colours use its 0-to-1 share (`score_weighted_share`), with a fixed threshold of
0.4 (colour cut-offs 0.6, 0.4, 0.2). No record gives a reason for the mix: the share came
with the wallet with sells (VI_202610_006) because a fixed threshold needs a fixed scale,
since the raw score moves with the date's rule weights and with how many rules a company is
measured on. The share is not neutral: a company measured on few rules (the floor is five
of ten) can reach a high share on little evidence, which puts SMCI first in the S&P 500
ranking by share (2026-10-31 data) while the picks are FSLR, SNA, CTSH and others. The
sell side has never been studied on its own (user, 2026-11-02).

Candidate: a moving threshold on the raw score, relative to the date (a bottom fraction
or a rank cut-off), tested as a methodology change with the S&P 500 baseline recorded
first, and the letters read before it (`AGENTS.md`, "Methodology vs refactor"). The user
noted (2026-11-02) that the cut-off was checked in an earlier optimisation without
showing a problem; that check is not in the records. Pencilled in for the study of the
sell and short optimisation, not before.

### Optimisation candidates (2026-11-01, open → S_202611_003, VI_202611_001)

Collected for the first study (user, 2026-11-01):

1. **More names per decision.** Telling people to buy two or three mega-caps is of little
   use, and the picks barely change between decisions. Search the number of names
   (`[wallet] names`, now 5; 10 and 20 to compare) and whether the signal lifts. If it does
   not, lengthen the time threshold (hold longer) so that more underdogs are picked.
2. **Rule ablation.** Remove one rule at a time and measure the change in the result; list
   the 10 rules with the highest impact. G2A equals E1, G2B equals E2 and G6 equals
   `pe_average`, so their joint effect is measured as one.
3. **Mean points per evaluable rule** in place of the sum (see the note above).
4. **Gates and weights**, filed under "Tried and not used" and "Rule weighting strategies".
5. **Rule windows**, with floors, as in VI_202611_001.
6. **Sector-neutral grades, and quality and growth in the rule set.** From the missed-winners
   check (VI_202611_001, check 24): the winners lacked dividends and traded at higher
   multiples, and our picks sit in the sectors that did not win (no health care on the S&P
   400, no energy on the 600). Hypotheses, to be tested on fresh data.
7. **Segment-selected rule sets** (user, 2026-11-01): with the ten default rules as the
   base, the optimisation may choose which rules apply to which company type (sector, size,
   dividend payer), tied to the switches of `assay/notes.md`; a studio-tier option.
8. **Price against value including growth** (the investor's answer, VI_202611_001, check
   28): a growth-adjusted P/E, later owner earnings, in place of the absolute P/E and
   price-to-book tests.
9. **Rule routing by a gate** (user, 2026-11-01: "if the gate says this, use this rule or
   that"): the best candidate so far is the price slot graded by PEG where B1 passes and by
   G6 elsewhere (VI_202611_001, check 30), +0.3 to +1 point a year, not yet adopted; a base
   for the segment-selected approach (candidate 7).

### The sample starts after the 2008 crisis (2026-11-01, open → VI_202611_001)

User, 2026-11-01: the first scored date is December 2009, just after the financial crisis,
a period of extreme stress when smaller companies became more unpredictable. Measured on
the S&P 500 (training companies, 36-month windows): the equal-weight universe beat the
total-return index by 3.7% a year over the dates 2009 to 2016 and by -0.3% over 2017 to
2026, and a random 10-name book beat the index in 73% of the 2009 to 2016 windows and 45%
of the later ones. So the early part of the sample is flattered, by the rebound or by the
current members (survivorship), and the later part is not. Hypotheses to test, not
findings: the rebound from the March 2009 low, the stress on smaller companies, falling
rates, and survivorship; the result without the early dates; each period separately. The
conclusions of VI_202611_001 must carry this note. The comparison of results with market
events and institutional logic is step 14 of the protocol in `quant.md`; whether a
separate reviewing hat (a Buffett hat) is needed is open (user).

### Index migration biases the 400 and 600 tables (2026-11-01, open → MD_202610_004)

A company is scored in an index's table only if it is a member of that index today (from its
`date_added`). One that grew from the S&P 600 into the 400 or 500 is missing from the 600
table in its small-cap years, and one that moved from the 500 to the 400 is in the 400 from
its listed date. So the 400 and 600 tables lose their best performers to the larger index
and the 500 keeps them from the date they joined; the indices' own lists give no entry
dates and flatter random books by size on top (VI_202611_001, check 20). The change
histories show 212 symbols in both the 500 and 400 lists. A combined S&P 1500 universe with
the index of each date (MD_202611_001) is the clean test of the same rules on smaller
companies. The 400's membership starts in 2012 and the 600's in 2019 (the first dates of
their change lists), which is why they have 47 and 28 scored dates against the 500's 68.
The data (prices, EDGAR facts) is already fetched for all three indices together; the
membership by date across them is what is missing. Postponed as a larger refactor (user,
2026-11-01).

### Tried and not used (2026-11-01, standing list → VI_202611_001)

Modifications that were tried and failed to add to the plain score are labelled *tried and
not used*, with their design, and are re-tested once the optimisation framework exists
(S_202611_003; user, 2026-11-01). They are not rejected for good: the S&P 500 sample is
short and was looked at.

| Date | Modification | Design (fixed before the run) | Result on the S&P 500 training companies |
|---|---|---|---|
| 2026-11-01 | Signed rule weights, also shrunk by instability | weights learned on training companies, 12 closed windows | no variant had a score correlation above 0.01 |
| 2026-11-01 | Ordered analysis (check 7) | G3, B1, G2B gates, then lowest G6, top 5 | trails the index at every horizon |
| 2026-11-01 | Gates then score, D1 to D3 (check 8) | G3 (10 y), or G3 + B1 + G2B, or G3 + G6 ceiling + B1 rank | below the plain score at every horizon |
| 2026-11-01 | Gates at 3-year windows, D5a and D5b (check 9) | G3; G3 + B1 + G2B at 3-year windows | no different from the plain score |
| 2026-11-01 | Buckets 10 with earnings averaged over 2 years (check 15) | other settings as the first light | +0.6 [-0.5, +1.0] points a year at 36 months, paired band includes zero |
| 2026-11-01 | A 3 by 3 grid of buckets (6, 8, 10) and averaging years (2, 3, 4) (check 17) | 8 paired comparisons, 99% band | none excludes zero; the surface is flat |
| 2026-11-01 | Dropping the price rules G6 and G7 (check 28) | on the ten rules | +5.3 [+1.2, +11.7] on the S&P 500 top 10 only; nothing on the 400, contradicted on the 600 |
| 2026-11-01 | PEG replacing or added to P/E (check 29) | three designs | not distinguishably more sensitive than G6 and G7 separately; the broad spread rises, the top 10 falls |
| 2026-11-01 | PEG routed by the quality gate B1 (check 30) | PEG where B1 passes, G6 elsewhere | +0.3 to +1 point a year; the strongest candidate, kept as a switch, not default |
| 2026-11-01 | Dropping one rule or group at a time (check 25) | 22 drops on three indices | the dividend rules make no measurable difference on the 500 and 400; no drop adopted |

### Unevaluable rules cost points in the binned score (2026-11-01, open → optimisation)

`score_binned` is the sum of points, so a company on which a rule cannot be evaluated
earns nothing there, and the score grows with the number of evaluable rules
(`scoring.py`). With the long windows it favoured companies with long histories: NVDA and
MSFT lost the G5 points in 2019 (VI_202611_001). The 3-year windows reduce the effect but
do not remove it. Candidate for the optimisation: the mean points per evaluable rule, or a
fixed rule set per date. A methodology change.

### Tag choice looks ahead (2026-10-31, resolved 2026-11-01 in MD_202610_002)

Found by a truncation test (VI_202610_006): cutting the facts at a decision date t
(filed <= t), prices and dividends at t, and recomputing the scores gives the same
scores on 2025-12-19, but on 2018-12-21 2 of 296 companies differ by one point and on
2022-12-16 3 differ in the plain grades and 1 in a pass/fail flag (which moves every
rule weight by about 0.01); the top five picks are the same on all three dates. Cause:
`market_data.clean.select_tags` chooses each company's tag by its most recent use over
all filings to the snapshot date, so the choice between two first-reported values
depends on later filings (Martin Marietta's intangible assets: price to tangible assets
5.07 cut, 4.23 full, on 2018-12-21). Fix: choose the tag from filings dated on or before
each decision date, and keep the truncation test as a unit test over every decision
date. A change to point-in-time handling: methodology, for the user to approve.
Approved and built 2026-11-01: the tag is chosen from the filings made by each date; the
truncation test passes on all three dates.

Other forward information the scores still carry, stated with every result: the
universe is today's S&P 500 members (companies that left the index are missing; those
that joined later are kept out only before their `date_added`); sectors are today's
GICS; and the score's design was chosen while looking at 2016 to 2026.

### The TFSA cannot hold individual shares (2026-10-31, open)

EasyEquities' own pages (2026): a tax-free savings account may hold only collective
investment schemes (JSE-listed ETFs and actively managed ETFs, unit trusts, bundles)
and SA government bonds, not individual shares, JSE or US; US shares sit in the
separate USD account, which is not tax-free. So no pick of the value wallet can be
bought in the TFSA. Consistent with the earlier note that the TFSA is a comparison
only and does not constrain where the sleeve is held. Options for the user: hold the
sleeve in the EasyEquities USD account (taxable; currency conversion and the
offshore allowance apply), or apply the score to JSE shares in the ZAR account
(a JSE universe, a new change). Sources: easyequities.co.za/tfsa-investing,
support.easyequities.co.za article 13000085076.

## Data issues

### Companies without usable EDGAR history (2026-10-31, open)

Found in the first buyability runs (VI_202610_002). Only the Yahoo rules (G4, E4) are
evaluable for these, so with the mean score they reach 0 or 1 on two rules:

- EMR, TRMB (CIK 864749) and VYLR have no rows in the 2026-10-31 `facts` snapshot.
  Check whether the EDGAR fetch failed or the CIK in the constituents table is wrong.
- XOM maps to CIK 2115436, ExxonMobil Holdings Corp, a 2026 holding company with only
  10-Q filings; Exxon's history is under its former CIK and is not linked. A
  predecessor-CIK mapping is needed for reorganisations like this.
- HONA (Honeywell Aerospace, CIK 2089271) is a 2026 spin-off with no 10-K yet: no
  history, correctly.

### A. O. Smith FY2024 10-K missing (2026-10-31, open)

AOS (CIK 91142): the FY2024 annual values appear only as comparatives in the FY2025
10-K filed 2026-02-10; the FY2024 10-K itself (due about February 2025) is not in the
snapshot. From 2025-09 to 2026-02 the latest annual year on file is FY2023, older than
550 days, so its history is dropped and its score falls from 9 to 2. Check the
companyfacts payload for the missing accession.

### Missing tags make rules unevaluable (2026-10-31, open)

Companies without debt often report no `long_term_debt` tag, and many report no
`goodwill` or `intangible_assets`. With a missing input giving NaN (decided 2026-10-31),
G2b, E2, B1 and E6 are not evaluable for them and score 0, which penalises a debt-free
company. To decide once the data has been looked at: treat an unreported debt or
goodwill tag in a 10-K that reports the balance sheet as 0, or keep NaN.

### Thin coverage at both ends of the score (2026-10-31, resolved)

With the sum score, the lowest mean scores from 2016 were companies with short or
missing history (GEV, SOLV, HONA and FDXF spin-offs, GDDY and DELL listings): mean
`n_available` 2 to 8 against a median of 13.4. The mean score (user, 2026-10-31) moves
the problem to both ends: a company evaluable on two rules scores 0 or 1 (EMR and XOM
top the 2016 sample at 1.00). A minimum `n_available` before a company is ranked would
keep the sample to companies measured on most rules. Decided 2026-10-31: at least 5
evaluable rules (VI_202610_002).

