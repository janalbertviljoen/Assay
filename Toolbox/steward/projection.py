"""
steward/projection.py
---------------------
The personal report's numbers: the net worth by part, the listed funds against their
guideline weights, the property company's monthly cash flow and the projection of its
value, bond and equity under each growth scenario.

Owns
----
Net worth, allocation gaps, the property's monthly cash flow and its projection.

Must not
--------
Read files or format text (``steward.__main__``, ``steward.report``); compute the
loan schedule (``skatkis.financial_logic.amortise``).

Public API
----------
net_worth(finances, usd_rate)
    Each part of the net worth in ZAR and its share.
allocation(finances)
    The listed funds' actual weights against their targets.
monthly_cash_flow(holding)
    A month's payments while the founder lives in the unit, and the extra into the bond.
property_projection(holding, growth)
    The property's value, bond, equity and loan to value at the end of each year.
property_stake(holding)
    The founder's stake in the property company at market value.
bond_payment(holding)
    The monthly payment into the bond.
repaid_after(holding)
    The years until the bond is repaid.
loan_repaid_after(balance, rate, payment)
    The years until a loan is repaid at a fixed monthly payment.
savings_projection(account, years, person=None)
    A savings account's value at the end of each year, with its monthly contribution.
listed_projection(finances, usd_rate, years)
    The listed accounts together, at the end of each year.
retirement_table(finances, usd_rate)
    Each part of the net worth today and at retirement, per property scenario.
tfsa_full_after(tfsa, monthly)
    The years until the tax-free account's lifetime limit is reached.
company_portfolio(holding, scenario, years)
    The property company's share portfolio, built from its profit once the bond is repaid.
loss_used_after(holding, scenario, years)
    The years until the company's assessed loss is used up (NaN if not within ``years``).

Computes
--------
net worth, share of net worth : net_worth
    Accounts at value (USD at ``usd_rate``); the property company's stake = market
    value + other assets - bond, the members' loan included (owed to the founder); the
    car at its value and its loan as a negative part.
allocation gap, weight against target : allocation
    target scaled to sum to 100; actual = value / sum of values, in percent; gap =
    actual - target, and in rand.
savings projection, future value of escalating monthly contributions : savings_projection
    V(m) = V(m-1) (1 + g_y)^(1/12) + c (1 + e)^y Π(1 + r_k), month by month, y the whole
    years elapsed, r_k the raises of years k <= y and g_y the phase growth of year y for
    a phased account (else its own growth); reported at each year end.
reinvested rental profit, company portfolio, assessed loss : company_portfolio
    While the bond runs: taxable result = rent paid - interest I(m) - levies - rates,
    nothing invested; a loss adds to the assessed loss, a profit uses it. From the
    month the bond is repaid: profit = rent (1 + g_r)^t - costs (1 + g_c)^t, t in years
    since; tax-free while the assessed loss lasts, then taxed at the company rate;
    P(m) = P(m-1) (1 + g_p)^(1/12) + profit after tax.
extra bond repayment : monthly_cash_flow
    extra = paid by the founder - (instalment + levies + rates); into the bond =
    instalment + extra.
property value projection, home equity, loan to value : property_projection
    V(y) = V(0) (1 + g)^y; B(y) from ``amortise`` at the monthly payment into the bond;
    equity = V - B; LTV = B / V.
retirement projection, value in today's money : retirement_table
    Each part at the retirement age: listed and retirement accounts by
    ``savings_projection``, the property at value less bond per scenario; the total
    also divided by (1 + inflation)^years.
tax-free account room : tfsa_full_after
    years = (lifetime limit - contributed) / min(12 monthly, annual limit).

Dependency rule
---------------
pandas, ``skatkis.financial_logic`` and ``steward.finances``.
"""

from dataclasses import replace

import pandas as pd

from Toolbox.skatkis.financial_logic import amortise
from Toolbox.steward.finances import Account, Finances, Person, Property, Tfsa

BOND_COSTS = ("bond_instalment", "levies", "property_rates")


def property_stake(holding: Property) -> float:
    """Return the founder's stake in the property company at market value (ZAR).

    Market value + other assets - bond: the members' loan is owed to the founder, so it
    is part of the stake, not a liability of the founder.
    """
    return holding.value + holding.other_assets - holding.bond


def net_worth(finances: Finances, usd_rate: float) -> pd.DataFrame:
    """Return each part of the net worth in ZAR, with its share.

    Columns ``part``, ``kind`` (``listed``, ``retirement`` or ``property``), ``value``
    and ``share`` (of the total, a fraction); USD accounts at ``usd_rate`` ZAR per USD.
    """
    rows = [
        {
            "part": a.name,
            "kind": a.kind,
            "value": a.value * (usd_rate if a.currency == "USD" else 1.0),
        }
        for a in finances.accounts
    ]
    rows.append(
        {
            "part": f"{finances.property.name} (stake at market value)",
            "kind": "property",
            "value": property_stake(finances.property),
        }
    )
    if finances.car is not None:
        rows.append({"part": "Car", "kind": "car", "value": finances.car.value})
        rows.append({"part": "Car loan", "kind": "debt", "value": -finances.car.loan})
    table = pd.DataFrame(rows)
    table["share"] = table["value"] / table["value"].sum()
    return table


def allocation(finances: Finances) -> pd.DataFrame:
    """Return the listed funds' actual weights against their targets.

    Columns ``fund``, ``target`` and ``actual`` (percent), ``gap`` (percentage points)
    and ``gap_value`` (ZAR), largest overweight first. The targets are scaled to sum to
    100, so dropping a fund spreads its weight over the others in proportion.
    """
    values = pd.Series(finances.holdings, dtype=float)
    total = float(values.sum())
    scale = 100 / sum(finances.targets.values())
    table = pd.DataFrame(
        {
            "fund": list(finances.targets),
            "target": [scale * finances.targets[f] for f in finances.targets],
            "actual": [100 * values.get(f, 0.0) / total for f in finances.targets],
        }
    )
    table["gap"] = table["actual"] - table["target"]
    table["gap_value"] = table["gap"] / 100 * total
    return table.sort_values("gap", ascending=False, ignore_index=True)


def monthly_cash_flow(holding: Property) -> pd.DataFrame:
    """Return a month's payments while the founder lives in the unit.

    Rows: what the founder pays, each cost, the extra into the bond and the total into
    the bond; column ``amount`` (ZAR, costs negative).
    """
    month = holding.monthly
    paid = month["paid_by_user"]
    costs = {k: month[k] for k in BOND_COSTS}
    extra = paid - sum(costs.values())
    rows = [("Paid by you", paid)]
    rows += [(k.replace("_", " ").capitalize(), -v) for k, v in costs.items()]
    rows += [
        ("Extra into the bond", extra),
        ("Into the bond in all", costs["bond_instalment"] + extra),
    ]
    return pd.DataFrame(rows, columns=["item", "amount"])


def bond_payment(holding: Property) -> float:
    """Return the monthly payment into the bond: the instalment plus the extra (ZAR)."""
    month = holding.monthly
    return month["paid_by_user"] - month["levies"] - month["property_rates"]


def property_projection(holding: Property, growth: float) -> pd.DataFrame:
    """Return the property's value, bond, equity and loan to value per year.

    Year 0 is today; the bond follows ``amortise`` at ``bond_payment`` a month and the
    value grows by ``growth`` a year. Columns ``year``, ``value``, ``bond``,
    ``equity`` (value - bond) and ``ltv`` (bond / value).
    """
    schedule = amortise(
        holding.bond,
        annual_rate=holding.rate,
        payment=bond_payment(holding),
        months=12 * holding.years,
    )
    rows: list[dict[str, float]] = []
    for year in range(holding.years + 1):
        value = holding.value * (1 + growth) ** year
        bond = (
            holding.bond
            if year == 0
            else float(schedule["balance"].iloc[12 * year - 1])
        )
        rows.append(
            {
                "year": float(year),
                "value": value,
                "bond": bond,
                "equity": value - bond,
                "ltv": bond / value,
            }
        )
    return pd.DataFrame(rows)


def repaid_after(holding: Property) -> float:
    """Return the years until the bond is repaid at ``bond_payment`` (NaN if never)."""
    return loan_repaid_after(holding.bond, holding.rate, bond_payment(holding))


def loan_repaid_after(balance: float, rate: float, payment: float) -> float:
    """Return the years until a loan is repaid at ``payment`` a month (NaN if never)."""
    schedule = amortise(balance, annual_rate=rate, payment=payment, months=12 * 40)
    done = schedule[schedule["balance"] <= 0]
    return float(done["month"].iloc[0]) / 12 if not done.empty else float("nan")


def savings_projection(
    account: Account, years: int, person: Person | None = None
) -> pd.DataFrame:
    """Return a savings account's value at the end of each year 0..``years``.

    The value grows at ``account.growth`` a year, or for a ``phased`` account at the
    ``person``'s risk phase of each year, compounded monthly, and receives
    ``account.monthly`` at the end of each month, raised by ``account.escalation`` at
    the start of each later year. Columns ``year`` and ``value``.
    """
    value = account.value
    rows = [{"year": 0.0, "value": value}]
    for month in range(1, 12 * years + 1):
        year = (month - 1) // 12
        growth = (
            person.growth_in_year(year, account.growth)
            if person is not None and account.phased
            else account.growth
        )
        factor = (1 + growth) ** (1 / 12)
        raised = (1 + account.escalation) ** year
        for start, rise in account.raises.items():
            if year >= start:
                raised *= 1 + rise
        value = value * factor + account.monthly * raised
        if month % 12 == 0:
            rows.append({"year": float(month // 12), "value": value})
    return pd.DataFrame(rows)


def listed_projection(finances: Finances, usd_rate: float, years: int) -> pd.DataFrame:
    """Return the listed accounts' combined value at the end of each year 0..``years``.

    Each account by ``savings_projection``; USD accounts at ``usd_rate`` (held fixed).
    Columns ``year`` and ``value``.
    """
    parts = [
        savings_projection(a, years, finances.person).set_index("year")["value"]
        * (usd_rate if a.currency == "USD" else 1.0)
        for a in finances.accounts
        if a.kind == "listed"
    ]
    total: pd.Series = pd.concat(parts, axis=1).sum(axis=1)
    return pd.DataFrame({"year": total.index.to_numpy(), "value": total.to_numpy()})


def retirement_table(finances: Finances, usd_rate: float) -> pd.DataFrame:
    """Return each part of the net worth today and at the retirement age.

    Rows: the listed accounts together, each retirement account and the property
    company; columns ``part``, ``today`` and one per growth scenario of the property
    (the accounts are the same in every scenario). The car is left out: its loan is
    repaid long before. Today the property counts at its stake (``property_stake``), at
    retirement at value less bond. The last two rows are the total and the total in
    today's money (divided by (1 + inflation)^years).

    Raises
    ------
    ValueError
        When ``finances.person`` is missing.
    """
    if finances.person is None:
        raise ValueError("the retirement projection needs [person] in the finances")
    person = finances.person
    years = person.retirement_age - person.age
    holding = finances.property
    scenarios = list(holding.growth)
    listed = listed_projection(finances, usd_rate, years)["value"]
    rows: list[dict[str, object]] = [
        {
            "part": "Listed funds",
            "today": float(listed.iloc[0]),
            **{name: float(listed.iloc[-1]) for name in scenarios},
        }
    ]
    for account in finances.accounts:
        if account.kind == "retirement":
            grown = savings_projection(account, years, person)["value"]
            rows.append(
                {
                    "part": account.name,
                    "today": account.value,
                    **{name: float(grown.iloc[-1]) for name in scenarios},
                }
            )
    if holding.after_bond is not None:
        rows.append(
            {
                "part": f"{holding.name} share portfolio (profits reinvested)",
                "today": 0.0,
                **{
                    name: float(
                        company_portfolio(holding, name, years, person)["value"].iloc[
                            -1
                        ]
                    )
                    for name in scenarios
                },
            }
        )
    longer = replace(holding, years=max(years, holding.years))
    rows.append(
        {
            "part": holding.name,
            "today": property_stake(holding),
            **{
                name: float(property_projection(longer, growth).iloc[years]["equity"])
                for name, growth in holding.growth.items()
            },
        }
    )
    table = pd.DataFrame(rows)
    total = {c: float(table[c].sum()) for c in ["today", *scenarios]}
    deflator = (1 + person.inflation) ** years
    rows.append({"part": "Total", **total})
    rows.append(
        {
            "part": "Total in today's money",
            "today": total["today"],
            **{name: total[name] / deflator for name in scenarios},
        }
    )
    return pd.DataFrame(rows)


def tfsa_full_after(tfsa: Tfsa, monthly: float) -> float:
    """Return the years until the tax-free account's lifetime limit is reached.

    Contributions of ``monthly`` a month, capped at the annual limit; NaN when nothing
    is contributed.
    """
    yearly = min(12 * monthly, tfsa.annual_limit)
    if yearly <= 0:
        return float("nan")
    return max(tfsa.lifetime_limit - tfsa.contributed, 0.0) / yearly


def company_portfolio(
    holding: Property, scenario: str, years: int, person: Person | None = None
) -> pd.DataFrame:
    """Return the property company's share portfolio at the end of each year.

    Nothing is invested while the bond is being repaid (at ``bond_payment`` a month, no
    draws); from the month after, the profit (``after_bond`` rent less costs, each grown
    from that month) goes into a portfolio growing at ``portfolio_growth``. The assessed
    loss is carried month by month (``_company_months``). Columns ``year`` and
    ``value``; all zero when ``after_bond`` is missing.
    """
    rows = [{"year": 0.0, "value": 0.0}]
    for month, value, _ in _company_months(holding, scenario, years, person):
        if month % 12 == 0:
            rows.append({"year": float(month // 12), "value": value})
    return pd.DataFrame(rows)


def loss_used_after(holding: Property, scenario: str, years: int) -> float:
    """Return the years until the assessed loss is used up (NaN if not within ``years``)."""
    for month, _, loss in _company_months(holding, scenario, years):
        if loss <= 0:
            return month / 12
    return float("nan")


def _company_months(
    holding: Property, scenario: str, years: int, person: Person | None = None
) -> list[tuple[int, float, float]]:
    """Return, per month, the company's share portfolio and its remaining assessed loss.

    While the bond runs the taxable result is ``rent_paid`` less the month's interest,
    levies and rates; a loss adds to the assessed loss and a profit uses it up (nothing
    is invested: the cash goes to the bond). After the bond, the letting profit is
    tax-free while the loss lasts, then taxed at ``company_tax``, and is invested.
    """
    after = holding.after_bond
    if after is None:
        return [(m, 0.0, 0.0) for m in range(1, 12 * years + 1)]
    schedule = amortise(
        holding.bond,
        annual_rate=holding.rate,
        payment=bond_payment(holding),
        months=12 * years,
    )
    repaid = schedule.index[schedule["balance"] <= 0]
    start = int(schedule["month"].iloc[repaid[0]]) if len(repaid) else 12 * years + 1
    month_costs = holding.monthly["levies"] + holding.monthly["property_rates"]
    rent_paid = holding.monthly.get("rent_paid", 0.0)
    value, loss = 0.0, after.assessed_loss
    out: list[tuple[int, float, float]] = []
    for month in range(1, 12 * years + 1):
        if month <= start:
            result = (
                rent_paid - float(schedule["interest"].iloc[month - 1]) - month_costs
            )
            loss = loss - result if result < 0 else max(loss - result, 0.0)
        else:
            elapsed = (month - start - 1) / 12
            profit = after.rent * (1 + after.rent_growth[scenario]) ** elapsed
            profit -= after.expenses * (1 + after.expense_growth) ** elapsed
            shielded = min(max(profit, 0.0), loss)
            loss -= shielded
            after_tax = (
                profit
                if profit < 0
                else shielded + (profit - shielded) * (1 - after.company_tax)
            )
            growth = (
                person.growth_in_year((month - 1) // 12, after.portfolio_growth)
                if person is not None and after.phased
                else after.portfolio_growth
            )
            value = value * (1 + growth) ** (1 / 12) + after_tax
        out.append((month, value, loss))
    return out
