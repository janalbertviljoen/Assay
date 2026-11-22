"""
steward/finances.py
-------------------
The founder's finances as the personal report reads them: the accounts, the property
company and the listed funds against their guideline weights.

The values come from the private input ``finances.toml`` in the private workspace, which
``steward.__main__`` reads; this module only turns the parsed mapping into typed
records. No figures live in the code or in any tracked file.

Owns
----
The structure of the private input.

Must not
--------
Read files (``steward.__main__``); project or summarise (``steward.projection``).

Public API
----------
Account(name, kind, value, currency, monthly, growth, escalation, source, raises)
    One account outside the property company.
Car(value, loan, rate, payment, insurance)
    The car and its loan.
Person(age, retirement_age, inflation, phases)
    The founder's age, retirement age, the inflation assumed for today's money and the
    risk phases.
Phase(name, until_age, growth)
    One risk phase: the yearly growth until an age.
Person.growth_in_year(year, default)
    The phase growth in a year from today, or ``default`` after the last phase.
Tfsa(contributed, lifetime_limit, annual_limit)
    What has gone into the tax-free account and its limits.
Property(name, value, cost, other_assets, bond, rate, members_loan, ...)
    The property company: value, bond and the monthly payments.
AfterBond(rent, expenses, expense_growth, portfolio_growth, company_tax, ...)
    The property company once its bond is repaid: rent, costs and reinvestment.
Finances(as_of, accounts, property, targets, holdings, car, person, tfsa, buy_list)
    Everything the personal report shows.
parse_finances(raw)
    The ``Finances`` of a parsed ``finances.toml``.

Dependency rule
---------------
The standard library only.
"""

import datetime
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Account:
    """One account outside the property company.

    ``kind`` is ``listed`` or ``retirement``; ``value`` is in ``currency``;
    ``monthly`` the regular contribution, ``growth`` the yearly growth assumed for its
    projection and ``escalation`` the yearly rise of the contribution (all 0 when not
    given); with ``phased`` the account grows at the founder's risk phases instead of
    ``growth``; ``raises`` maps a year from today to a one-off rise of the contribution
    from the start of that year (a promotion).
    """

    name: str
    kind: str
    value: float
    currency: str
    monthly: float
    growth: float
    escalation: float
    source: str
    raises: Mapping[int, float] = field(default_factory=dict[int, float])
    phased: bool = False


@dataclass(frozen=True)
class AfterBond:
    """The property company once its bond is repaid.

    The unit is let at ``rent`` a month with ``expenses`` a month of costs; the rent
    grows by ``rent_growth`` of the scenario a year and the costs by ``expense_growth``.
    The profit, after ``company_tax`` once the ``assessed_loss`` is used up, is
    reinvested in shares growing ``portfolio_growth`` a year.
    """

    rent: float
    expenses: float
    expense_growth: float
    portfolio_growth: float
    company_tax: float
    assessed_loss: float
    rent_growth: Mapping[str, float]
    phased: bool = False


@dataclass(frozen=True)
class Car:
    """The car and its loan.

    ``value`` is the car's value, ``loan`` what is owed at ``rate`` a year, ``payment``
    the monthly repayment and ``insurance`` the monthly premium.
    """

    value: float
    loan: float
    rate: float
    payment: float
    insurance: float


@dataclass(frozen=True)
class Property:
    """The property company.

    ``value`` is the estimated market value, ``cost`` the book value, ``other_assets``
    the company's other assets (furniture, tax asset), ``bond`` the loan to project
    from, at ``rate`` a year; ``members_loan`` is owed to the founder. ``growth`` maps a
    scenario's name to its yearly growth of the value; ``monthly`` the payments of a
    month while the founder lives in the unit.
    """

    name: str
    value: float
    cost: float
    other_assets: float
    bond: float
    bond_note: str
    rate: float
    members_loan: float
    years: int
    horizons: Sequence[int]
    growth: Mapping[str, float]
    monthly: Mapping[str, float]
    after_bond: AfterBond | None = None


@dataclass(frozen=True)
class Phase:
    """One risk phase: ``growth`` a year until the founder reaches ``until_age``."""

    name: str
    until_age: int
    growth: float


@dataclass(frozen=True)
class Person:
    """The founder's ``age`` today, ``retirement_age`` and the yearly ``inflation``
    assumed to state future amounts in today's money.
    """

    age: int
    retirement_age: int
    inflation: float
    phases: Sequence[Phase] = ()

    def growth_in_year(self, year: int, default: float) -> float:
        """Return the phase growth in ``year`` from today (0 = this year).

        The first phase whose ``until_age`` is above the age in that year; ``default``
        when no phase covers it.
        """
        age = self.age + year
        for phase in self.phases:
            if age < phase.until_age:
                return phase.growth
        return default


@dataclass(frozen=True)
class Tfsa:
    """What has been ``contributed`` to the tax-free account and its ``lifetime_limit``
    and ``annual_limit`` (ZAR).
    """

    contributed: float
    lifetime_limit: float
    annual_limit: float


@dataclass(frozen=True)
class Finances:
    """Everything the personal report shows.

    ``targets`` are the listed funds' guideline weights in percent and ``holdings``
    their actual values, by fund; ``buy_list`` the investor's own ``currency``,
    ``picks_amount`` and ``fixed`` purchases for the value tool's buy list.
    """

    as_of: datetime.date
    accounts: Sequence[Account]
    property: Property
    targets: Mapping[str, float]
    holdings: Mapping[str, float]
    car: Car | None = None
    person: Person | None = None
    tfsa: Tfsa | None = None
    buy_list: Mapping[str, Any] = field(default_factory=dict[str, Any])


def parse_finances(raw: Mapping[str, Any]) -> Finances:
    """Return the ``Finances`` of a parsed ``finances.toml``.

    Raises
    ------
    KeyError
        When a required field is missing.
    ValueError
        When an account's ``kind`` is not ``listed`` or ``retirement``.
    """
    accounts: list[Account] = []
    for entry in raw["accounts"]:
        kind = str(entry["kind"])
        if kind not in {"listed", "retirement"}:
            raise ValueError(f"account {entry['name']!r}: unknown kind {kind!r}")
        accounts.append(
            Account(
                name=str(entry["name"]),
                kind=kind,
                value=float(entry["value"]),
                currency=str(entry.get("currency", "ZAR")),
                monthly=float(entry.get("monthly", 0.0)),
                growth=float(entry.get("growth", 0.0)),
                escalation=float(entry.get("escalation", 0.0)),
                raises={int(k): float(v) for k, v in entry.get("raises", {}).items()},
                phased=bool(entry.get("phased", False)),
                source=str(entry.get("source", "")),
            )
        )
    spec = raw["property"]
    holding = Property(
        name=str(spec["name"]),
        value=float(spec["value"]),
        cost=float(spec["cost"]),
        other_assets=float(spec["other_assets"]),
        bond=float(spec["bond"]),
        bond_note=str(spec.get("bond_note", "")),
        rate=float(spec["rate"]),
        members_loan=float(spec["members_loan"]),
        years=int(spec["years"]),
        horizons=[int(h) for h in spec["horizons"]],
        growth={str(k): float(v) for k, v in spec["growth"].items()},
        monthly={str(k): float(v) for k, v in spec["monthly"].items()},
        after_bond=_after_bond(spec.get("after_bond")),
    )
    car = raw.get("car")
    person = raw.get("person")
    tfsa = raw.get("tfsa")
    as_of = raw["as_of"]
    return Finances(
        as_of=(
            as_of
            if isinstance(as_of, datetime.date)
            else datetime.date.fromisoformat(str(as_of))
        ),
        accounts=accounts,
        property=holding,
        targets={str(k): float(v) for k, v in raw["targets"].items()},
        holdings={str(k): float(v) for k, v in raw["holdings"].items()},
        car=(
            Car(
                value=float(car["value"]),
                loan=float(car["loan"]),
                rate=float(car["rate"]),
                payment=float(car["payment"]),
                insurance=float(car["insurance"]),
            )
            if car is not None
            else None
        ),
        person=(
            Person(
                age=int(person["age"]),
                retirement_age=int(person["retirement_age"]),
                inflation=float(person["inflation"]),
                phases=[
                    Phase(
                        name=str(p["name"]),
                        until_age=int(p["until_age"]),
                        growth=float(p["growth"]),
                    )
                    for p in person.get("phases", [])
                ],
            )
            if person is not None
            else None
        ),
        buy_list=dict(raw.get("buy_list", {})),
        tfsa=(
            Tfsa(
                contributed=float(tfsa["contributed"]),
                lifetime_limit=float(tfsa["lifetime_limit"]),
                annual_limit=float(tfsa["annual_limit"]),
            )
            if tfsa is not None
            else None
        ),
    )


def _after_bond(spec: Mapping[str, Any] | None) -> AfterBond | None:
    """Return the ``[property.after_bond]`` settings, or None when not given."""
    if spec is None:
        return None
    return AfterBond(
        rent=float(spec["rent"]),
        expenses=float(spec["expenses"]),
        expense_growth=float(spec["expense_growth"]),
        portfolio_growth=float(spec["portfolio_growth"]),
        company_tax=float(spec["company_tax"]),
        assessed_loss=float(spec["assessed_loss"]),
        rent_growth={str(k): float(v) for k, v in spec["rent_growth"].items()},
        phased=bool(spec.get("phased", False)),
    )
