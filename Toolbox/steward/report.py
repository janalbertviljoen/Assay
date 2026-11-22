"""
steward/report.py
-----------------
Assembles the personal report: the whole portfolio, the property company's cash flow and
projection, then the value picks and the buy list of ``value_investing``.

The text is private, in ``data/private/steward/report_text.toml``; this
module fills it from the private finances and builds the tables. ``skatkis.report``
writes the LaTeX. The report is private and is written only under ``data/private/``.

Owns
----
The personal report's facts, tables and the order of its sections.

Must not
--------
Project (``steward.projection``); plot (``steward.plots``); build the value picks'
sections (``value_investing.report.buy_report_sections``).

Public API
----------
PersonalReport(finances, buy, usd_rate, property_figure)
    What the personal report shows.
personal_facts(inputs)
    The values of the personal text's placeholders.
build_personal_report(inputs, text, value_text, *, folder, subtitle)
    Write ``personal_report.tex`` and return its path.

Dependency rule
---------------
``skatkis.report``, ``steward`` and ``value_investing.report``.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from Toolbox.skatkis.report import Document, ReportFigure, Section, Table, write_latex
from Toolbox.steward import projection
from Toolbox.steward.finances import Finances
from Toolbox.value_investing.report import BuyReport, buy_report_sections


@dataclass(frozen=True)
class PersonalReport:
    """What the personal report shows.

    ``usd_rate`` is ZAR per USD for the USD accounts; ``property_figure`` the saved
    ``steward.plots.property_paths`` figure.
    """

    finances: Finances
    buy: BuyReport
    usd_rate: float
    property_figure: Path


def _rand(value: float) -> str:
    """Return ``value`` as whole rand with thousands separators, the sign first."""
    return f"-R{-value:,.0f}" if value < 0 else f"R{value:,.0f}"


def personal_facts(inputs: PersonalReport) -> dict[str, str]:
    """Return the values of the personal text's placeholders."""
    holding = inputs.finances.property
    worth = projection.net_worth(inputs.finances, inputs.usd_rate)
    by_kind = worth.groupby("kind")["value"].sum()
    total = float(worth["value"].sum())
    gaps = projection.allocation(inputs.finances)
    month = projection.monthly_cash_flow(holding).set_index("item")["amount"]
    facts = {
        "net_worth": _rand(total),
        "listed": _rand(float(by_kind.get("listed", 0.0))),
        "retirement": _rand(float(by_kind.get("retirement", 0.0))),
        "property_stake": _rand(float(by_kind.get("property", 0.0))),
        "property_share": f"{float(by_kind.get('property', 0.0)) / total:.0%}",
        "property_name": holding.name,
        "property_value": _rand(holding.value),
        "bond": _rand(holding.bond),
        "bond_note": holding.bond_note,
        "rate": f"{holding.rate:.1%}",
        "into_bond": _rand(float(month["Into the bond in all"])),
        "extra": _rand(float(month["Extra into the bond"])),
        "repaid_years": f"{projection.repaid_after(holding):.1f}",
        "largest_overweight": str(gaps["fund"].iloc[0]),
        "largest_overweight_gap": f"{float(gaps['gap'].iloc[0]):+.1f}",
        "largest_underweight": str(gaps["fund"].iloc[-1]),
        "largest_underweight_gap": f"{float(gaps['gap'].iloc[-1]):+.1f}",
        "horizon_end": str(holding.years),
        "members_loan": _rand(holding.members_loan),
        "property_cost": _rand(holding.cost),
        "usd_rate": f"{inputs.usd_rate:.2f}",
    }
    facts.update(_car_facts(inputs))
    facts.update(_saving_facts(inputs))
    # Scenario placeholders are keyed by position (1, 2, ...), never by their rate, so
    # changing a rate in the finances cannot break the text.
    for i, (name, growth) in enumerate(holding.growth.items(), start=1):
        table = projection.property_projection(holding, growth)
        facts[f"scenario_{i}"] = name
        facts[f"growth_{i}"] = f"{growth:.0%}"
        facts[f"equity_end_{i}"] = _rand(float(table["equity"].iloc[-1]))
    return facts


def _car_facts(inputs: PersonalReport) -> dict[str, str]:
    """Return the car's placeholders, or none when the finances give no car."""
    car = inputs.finances.car
    if car is None:
        return {}
    repaid = projection.loan_repaid_after(car.loan, car.rate, car.payment)
    return {
        "car_value": _rand(car.value),
        "car_loan": _rand(car.loan),
        "car_rate": f"{car.rate:.1%}",
        "car_payment": _rand(car.payment),
        "car_insurance": _rand(car.insurance),
        "car_repaid_years": f"{repaid:.1f}",
    }


def _saving_facts(inputs: PersonalReport) -> dict[str, str]:
    """Return the placeholders of the savings, the tax-free account and retirement."""
    holding = inputs.finances.property
    facts: dict[str, str] = {}
    person = inputs.finances.person
    if person is not None and person.phases:
        steps = [f"{p.growth:.0%} until {p.until_age}" for p in person.phases]
        facts["phases"] = ", ".join(steps[:-1]) + " and " + steps[-1]
    for account in inputs.finances.accounts:
        if account.kind == "retirement" and account.growth > 0:
            grown = projection.savings_projection(account, holding.years)
            facts["retirement_growth"] = f"{account.growth:.0%}"
            facts["retirement_monthly"] = _rand(account.monthly)
            facts["retirement_escalation"] = f"{account.escalation:.1%}"
            for j, horizon in enumerate(holding.horizons, start=1):
                end = grown[grown["year"] == float(horizon)]
                facts[f"horizon_{j}"] = str(horizon)
                facts[f"retirement_h{j}"] = _rand(float(end["value"].iloc[0]))
    if person is not None:
        retire = projection.retirement_table(inputs.finances, inputs.usd_rate)
        by_part = {str(r["part"]): r for r in retire.to_dict("records")}
        facts["age"] = str(person.age)
        facts["retirement_age"] = str(person.retirement_age)
        facts["years_to_retire"] = str(person.retirement_age - person.age)
        facts["inflation"] = f"{person.inflation:.0%}"
        company = [k for k in by_part if k.endswith("(profits reinvested)")]
        for i, name in enumerate(holding.growth, start=1):
            facts[f"total_end_{i}"] = _rand(float(by_part["Total"][name]))
            facts[f"real_end_{i}"] = _rand(
                float(by_part["Total in today's money"][name])
            )
            facts[f"company_end_{i}"] = (
                _rand(float(by_part[company[0]][name])) if company else "R0"
            )
        after = holding.after_bond
        if after is not None:
            facts["after_rent"] = _rand(after.rent)
            facts["after_expenses"] = _rand(after.expenses)
            facts["assessed_loss"] = _rand(after.assessed_loss)
            facts["rent_paid"] = _rand(holding.monthly.get("rent_paid", 0.0))
            facts["company_tax"] = f"{after.company_tax:.0%}"
            years = person.retirement_age - person.age
            for i, name in enumerate(holding.growth, start=1):
                used = projection.loss_used_after(holding, name, years)
                facts[f"loss_used_{i}"] = f"{used:.1f}"
        facts["listed_end"] = _rand(
            float(by_part["Listed funds"][next(iter(holding.growth))])
        )
    listed = [a for a in inputs.finances.accounts if a.kind == "listed"]
    monthly = sum(a.monthly for a in listed)
    facts["listed_monthly"] = _rand(monthly)
    tfsa = inputs.finances.tfsa
    if tfsa is not None:
        facts["tfsa_room"] = _rand(tfsa.lifetime_limit - tfsa.contributed)
        facts["tfsa_full_years"] = f"{projection.tfsa_full_after(tfsa, monthly):.0f}"
    return facts


def _worth_table(inputs: PersonalReport) -> Table:
    """Return the net worth by part, with the total."""
    worth = projection.net_worth(inputs.finances, inputs.usd_rate)
    rows = [
        [str(r["part"]), _rand(float(r["value"])), f"{float(r['share']):.0%}"]
        for r in worth.to_dict("records")
    ]
    rows.append(["Total", _rand(float(worth["value"].sum())), "100%"])
    return Table(
        header=["Part", "Value", "Share"],
        rows=rows,
        columns="l r r",
        breaks=[len(worth) - 1],
    )


def _allocation_table(inputs: PersonalReport) -> Table:
    """Return the listed funds against their guideline weights."""
    gaps = projection.allocation(inputs.finances)
    rows = [
        [
            str(r["fund"]),
            f"{float(r['target']):.0f}%",
            f"{float(r['actual']):.1f}%",
            f"{float(r['gap']):+.1f}",
            _rand(float(r["gap_value"])),
        ]
        for r in gaps.to_dict("records")
    ]
    return Table(
        header=["Fund", "Target", "Actual", "Gap (points)", "Gap (rand)"],
        rows=rows,
        columns="l r r r r",
    )


def _cash_flow_table(inputs: PersonalReport) -> Table:
    """Return a month's payments while living in the unit."""
    month = projection.monthly_cash_flow(inputs.finances.property)
    rows = [
        [str(r["item"]), _rand(float(r["amount"]))] for r in month.to_dict("records")
    ]
    return Table(
        header=["Each month", "Rand"],
        rows=rows,
        columns="l r",
        breaks=[len(month) - 3],
    )


def _projection_table(inputs: PersonalReport) -> Table:
    """Return value, bond, equity and loan to value per scenario and horizon."""
    holding = inputs.finances.property
    rows: list[list[str]] = [
        [
            "Today",
            "",
            _rand(holding.value),
            _rand(holding.bond),
            _rand(holding.value - holding.bond),
            f"{holding.bond / holding.value:.0%}",
        ]
    ]
    for name, growth in holding.growth.items():
        table = projection.property_projection(holding, growth)
        for horizon in holding.horizons:
            r = table[table["year"] == float(horizon)].iloc[0].to_dict()
            rows.append(
                [
                    f"In {horizon} years",
                    name,
                    _rand(float(r["value"])),
                    _rand(float(r["bond"])),
                    _rand(float(r["equity"])),
                    f"{float(r['ltv']):.0%}",
                ]
            )
    return Table(
        header=["When", "Scenario", "Value", "Bond", "Equity", "Loan to value"],
        rows=rows,
        columns="l l r r r r",
        breaks=[0],
    )


def _retirement_sections(
    inputs: PersonalReport, text: Mapping[str, Any], fill: Callable[[object], str]
) -> list[Section]:
    """Return the retirement section, or none when the finances give no ages."""
    if inputs.finances.person is None:
        return []
    spec = text["retirement"]
    return [
        Section(
            title=fill(spec["title"]),
            text=fill(spec["text"]),
            table=replace(
                _retirement_table(inputs),
                caption=fill(spec["caption"]),
                label="tab:retirement",
            ),
        )
    ]


def _retirement_table(inputs: PersonalReport) -> Table:
    """Return each part today and at the retirement age, per property scenario."""
    retire = projection.retirement_table(inputs.finances, inputs.usd_rate)
    growth = inputs.finances.property.growth
    scenarios = list(growth)
    age = inputs.finances.person.retirement_age if inputs.finances.person else 0
    rows = [
        [str(r["part"]), _rand(float(r["today"]))]
        + [_rand(float(r[name])) for name in scenarios]
        for r in retire.to_dict("records")
    ]
    return Table(
        header=["Part", "Today", *[f"At {age} ({growth[n]:.0%})" for n in scenarios]],
        rows=rows,
        columns="l r" + " r" * len(scenarios),
        breaks=[len(retire) - 3],
    )


def build_personal_report(
    inputs: PersonalReport,
    text: Mapping[str, Any],
    value_text: Mapping[str, Any],
    *,
    folder: Path,
    subtitle: str,
) -> Path:
    """Write the personal report's LaTeX into ``folder`` and return its path.

    ``text`` is the private report text, ``value_text`` the value report's text
    (for the picks' sections).
    """
    picks_sections, value_facts = buy_report_sections(inputs.buy, value_text)
    facts = {**value_facts, **personal_facts(inputs)}

    def fill(value: object) -> str:
        return str(value).format(**facts)

    portfolio = text["portfolio"]
    holding = text["property"]
    sections = [
        Section(
            title=fill(portfolio["title"]),
            text=fill(portfolio["text"]),
            table=replace(
                _worth_table(inputs),
                caption=fill(portfolio["worth_caption"]),
                label="tab:worth",
            ),
            subsections=[
                Section(
                    title=fill(portfolio["allocation_title"]),
                    text=fill(portfolio["allocation_text"]),
                    table=replace(
                        _allocation_table(inputs),
                        caption=fill(portfolio["allocation_caption"]),
                        label="tab:allocation",
                    ),
                )
            ],
        ),
        Section(
            title=fill(holding["title"]),
            text=fill(holding["text"]),
            table=replace(
                _cash_flow_table(inputs),
                caption=fill(holding["cash_caption"]),
                label="tab:cash",
            ),
            subsections=[
                Section(
                    title=fill(holding["projection_title"]),
                    text=fill(holding["projection_text"]),
                    table=replace(
                        _projection_table(inputs),
                        caption=fill(holding["projection_caption"]),
                        label="tab:projection",
                    ),
                    figures=[
                        ReportFigure(
                            inputs.property_figure,
                            fill(holding["figure"]),
                            label="fig:projection",
                        )
                    ],
                )
            ],
        ),
        *_retirement_sections(inputs, text, fill),
        *picks_sections,
    ]
    document = Document(
        title=fill(text["title"]),
        subtitle=subtitle,
        abstract=fill(text["abstract"]),
        sections=sections,
        contents=False,
    )
    return write_latex(folder / "personal_report.tex", document)
