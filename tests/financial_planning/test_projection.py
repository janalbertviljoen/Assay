"""The personal report's numbers (steward/projection.py)."""

import math
from dataclasses import replace
from typing import Any

import pandas as pd
import pytest

from Toolbox.steward import projection
from Toolbox.steward.finances import (
    Account,
    AfterBond,
    Finances,
    Person,
    Phase,
    Property,
    Tfsa,
    parse_finances,
)

USD_RATE = 20.0


@pytest.fixture
def finances(raw: dict[str, Any]) -> Finances:
    return parse_finances(raw)


def _account(**fields: Any) -> Account:
    base: dict[str, Any] = {
        "name": "Saver",
        "kind": "listed",
        "value": 1000.0,
        "currency": "ZAR",
        "monthly": 0.0,
        "growth": 0.0,
        "escalation": 0.0,
        "source": "",
    }
    return Account(**{**base, **fields})


# --- net worth and allocation --------------------------------------------------------


def test_net_worth_by_part(finances: Finances) -> None:
    worth = projection.net_worth(finances, USD_RATE)
    assert worth["part"].tolist() == [
        "Fund A",
        "Fund B",
        "Pension",
        "PropCo (stake at market value)",
        "Car",
        "Car loan",
    ]
    assert worth["kind"].tolist() == [
        "listed",
        "listed",
        "retirement",
        "property",
        "car",
        "debt",
    ]
    # USD at 20; the stake is 20 000 + 500 - 18 000, the members' loan not deducted.
    assert worth["value"].tolist() == [1000.0, 2000.0, 3000.0, 2500.0, 2000.0, -1800.0]
    assert worth["share"].tolist() == pytest.approx(
        [v / 8700 for v in [1000, 2000, 3000, 2500, 2000, -1800]]
    )


def test_net_worth_without_a_car(finances: Finances) -> None:
    worth = projection.net_worth(replace(finances, car=None), USD_RATE)
    assert "car" not in set(worth["kind"])
    assert worth["value"].sum() == 8500.0
    assert worth["share"].sum() == pytest.approx(1.0)


def test_property_stake(finances: Finances) -> None:
    assert projection.property_stake(finances.property) == 2500.0


def test_allocation_rescales_the_targets_to_100(finances: Finances) -> None:
    # Targets 30, 30, 20 sum to 80 -> 37.5, 37.5, 25; actual 50, 30, 20 of 1000.
    gaps = projection.allocation(finances)
    assert gaps["fund"].tolist() == ["X", "Z", "Y"]  # largest overweight first
    assert gaps["target"].tolist() == pytest.approx([37.5, 25.0, 37.5])
    assert gaps["actual"].tolist() == pytest.approx([50.0, 20.0, 30.0])
    assert gaps["gap"].tolist() == pytest.approx([12.5, -5.0, -7.5])
    assert gaps["gap_value"].tolist() == pytest.approx([125.0, -50.0, -75.0])


def test_allocation_fund_without_holding_is_at_0(finances: Finances) -> None:
    gaps = projection.allocation(replace(finances, targets={"X": 50.0, "Q": 50.0}))
    assert gaps.set_index("fund").loc["Q", "actual"] == 0.0
    assert gaps.set_index("fund").loc["Q", "gap"] == -50.0


# --- the property's month and its projection -----------------------------------------


def test_monthly_cash_flow(finances: Finances) -> None:
    month = projection.monthly_cash_flow(finances.property)
    assert month["item"].tolist() == [
        "Paid by you",
        "Bond instalment",
        "Levies",
        "Property rates",
        "Extra into the bond",
        "Into the bond in all",
    ]
    # Extra = 1100 - (600 + 50 + 50) = 400; into the bond 600 + 400.
    assert month["amount"].tolist() == [1100.0, -600.0, -50.0, -50.0, 400.0, 1000.0]


def test_bond_payment_is_the_instalment_plus_the_extra(finances: Finances) -> None:
    assert projection.bond_payment(finances.property) == 1000.0


def test_property_projection(finances: Finances) -> None:
    # 18 000 at 0% and 1000 a month: 6000 left after a year.
    table = projection.property_projection(finances.property, 0.1)
    assert table["year"].tolist() == [0.0, 1.0]
    assert table["value"].tolist() == pytest.approx([20000.0, 22000.0])
    assert table["bond"].tolist() == pytest.approx([18000.0, 6000.0])
    assert table["equity"].tolist() == pytest.approx([2000.0, 16000.0])
    assert table["ltv"].tolist() == pytest.approx([0.9, 6000 / 22000])


def test_property_projection_bond_stays_0_once_repaid(finances: Finances) -> None:
    table = projection.property_projection(replace(finances.property, years=3), 0.0)
    assert table["bond"].tolist() == pytest.approx([18000.0, 6000.0, 0.0, 0.0])
    assert table["ltv"].iloc[-1] == 0.0


def test_repaid_after(finances: Finances) -> None:
    assert projection.repaid_after(finances.property) == 1.5


def test_loan_repaid_after() -> None:
    assert projection.loan_repaid_after(1000.0, 0.0, 100.0) == pytest.approx(10 / 12)
    # 1% a month on 100 at 60: repaid in the second month.
    assert projection.loan_repaid_after(100.0, 0.12, 60.0) == pytest.approx(2 / 12)


def test_loan_never_repaid_is_nan() -> None:
    assert math.isnan(projection.loan_repaid_after(1000.0, 0.12, 5.0))


# --- savings -------------------------------------------------------------------------


def test_savings_projection_contributions_without_growth() -> None:
    table = projection.savings_projection(_account(monthly=100.0), 2)
    assert table["year"].tolist() == [0.0, 1.0, 2.0]
    assert table["value"].tolist() == pytest.approx([1000.0, 2200.0, 3400.0])


def test_savings_projection_zero_years_is_today_only() -> None:
    table = projection.savings_projection(_account(monthly=100.0), 0)
    assert table.to_dict("records") == [{"year": 0.0, "value": 1000.0}]


def test_savings_projection_growth_compounds_monthly_to_the_year() -> None:
    table = projection.savings_projection(_account(growth=0.21), 2)
    assert table["value"].tolist() == pytest.approx([1000.0, 1210.0, 1464.1])


def test_savings_projection_contributions_at_month_end_after_growth() -> None:
    # Future value of 12 end-of-month payments at the monthly factor f = 1.21^(1/12).
    f = 1.21 ** (1 / 12)
    table = projection.savings_projection(
        _account(value=0.0, monthly=100.0, growth=0.21), 1
    )
    assert table["value"].iloc[-1] == pytest.approx(100 * (f**12 - 1) / (f - 1))


def test_savings_projection_escalation_rises_each_year() -> None:
    # 12 x 100, then 12 x 110.
    table = projection.savings_projection(_account(monthly=100.0, escalation=0.1), 2)
    assert table["value"].tolist() == pytest.approx([1000.0, 2200.0, 3520.0])


def test_savings_projection_raise_from_its_year_compounds_with_escalation() -> None:
    # Year 0: 12 x 100; year 1: 12 x 100 x 1.1 x 1.5 = 12 x 165.
    account = _account(monthly=100.0, escalation=0.1, raises={1: 0.5})
    table = projection.savings_projection(account, 2)
    assert table["value"].tolist() == pytest.approx([1000.0, 2200.0, 4180.0])


def test_savings_projection_phased_account_follows_the_phases() -> None:
    # Age 40: year 0 at 21%, year 1 at 44%; the account's own growth after the phases.
    person = Person(
        age=40,
        retirement_age=65,
        inflation=0.05,
        phases=[Phase("growth", 41, 0.21), Phase("steady", 42, 0.44)],
    )
    phased = _account(growth=0.0, phased=True)
    table = projection.savings_projection(phased, 3, person)
    assert table["value"].tolist() == pytest.approx([1000.0, 1210.0, 1742.4, 1742.4])
    # Not phased, or no person: the account's own growth.
    plain = projection.savings_projection(_account(growth=0.0), 3, person)
    assert plain["value"].tolist() == pytest.approx([1000.0] * 4)
    alone = projection.savings_projection(phased, 3)
    assert alone["value"].tolist() == pytest.approx([1000.0] * 4)


def test_listed_projection_sums_the_listed_accounts_in_rand(finances: Finances) -> None:
    # Fund A 1000 + 1200 a year, Fund B 100 USD at 20; the pension is left out.
    table = projection.listed_projection(finances, USD_RATE, 2)
    assert table["year"].tolist() == [0.0, 1.0, 2.0]
    assert table["value"].tolist() == pytest.approx([3000.0, 4200.0, 5400.0])


# --- retirement ----------------------------------------------------------------------


def test_retirement_table(finances: Finances) -> None:
    # Two years to 62: listed 5400; pension 3000 x 1.1^2 = 3630; the property's bond is
    # repaid by then, so value less bond is 20 000 (low) and 24 200 (high).
    table = projection.retirement_table(finances, USD_RATE).set_index("part")
    assert table.index.tolist() == [
        "Listed funds",
        "Pension",
        "PropCo",
        "Total",
        "Total in today's money",
    ]
    assert table["today"].tolist() == pytest.approx([3000, 3000, 2500, 8500, 8500])
    assert table["low"].tolist() == pytest.approx(
        [5400, 3630, 20000, 29030, 29030 / 1.21]
    )
    assert table["high"].tolist() == pytest.approx(
        [5400, 3630, 24200, 33230, 33230 / 1.21]
    )


def test_retirement_table_needs_the_person(finances: Finances) -> None:
    with pytest.raises(ValueError, match=r"needs \[person\]"):
        projection.retirement_table(replace(finances, person=None), USD_RATE)


def test_retirement_table_adds_the_company_portfolio(finances: Finances) -> None:
    holding = _company(finances.property)
    table = projection.retirement_table(replace(finances, property=holding), USD_RATE)
    row = table.set_index("part").loc["PropCo share portfolio (profits reinvested)"]
    assert row["today"] == 0.0
    expected = projection.company_portfolio(holding, "low", 2)["value"].iloc[-1]
    assert row["low"] == pytest.approx(expected)


# --- tax-free account ----------------------------------------------------------------


TFSA = Tfsa(contributed=100000.0, lifetime_limit=500000.0, annual_limit=36000.0)


def test_tfsa_full_after() -> None:
    assert projection.tfsa_full_after(TFSA, 1000.0) == pytest.approx(400000 / 12000)


def test_tfsa_full_after_capped_at_the_annual_limit() -> None:
    assert projection.tfsa_full_after(TFSA, 5000.0) == pytest.approx(400000 / 36000)
    assert projection.tfsa_full_after(TFSA, 3000.0) == pytest.approx(400000 / 36000)


def test_tfsa_full_after_nothing_contributed_is_nan() -> None:
    assert math.isnan(projection.tfsa_full_after(TFSA, 0.0))


def test_tfsa_full_after_limit_reached_is_0() -> None:
    full = Tfsa(contributed=600000.0, lifetime_limit=500000.0, annual_limit=36000.0)
    assert projection.tfsa_full_after(full, 1000.0) == 0.0


# --- the company's portfolio after the bond ------------------------------------------


def _company(holding: Property, **after: Any) -> Property:
    """Bond 2000 at 0% and 1000 a month: repaid in month 2, so profit from month 3."""
    plan: dict[str, Any] = {
        "rent": 400.0,
        "expenses": 100.0,
        "expense_growth": 0.0,
        "portfolio_growth": 0.0,
        "company_tax": 0.25,
        "assessed_loss": 300.0,
        "rent_growth": {"low": 0.0, "high": 0.0},
    }
    return replace(holding, bond=2000.0, after_bond=AfterBond(**{**plan, **after}))


def test_company_portfolio_uses_the_assessed_loss_then_pays_tax(
    finances: Finances,
) -> None:
    # Months 1-2 (bond): 0 - 0 - 100 a month adds 200 to the loss of 300 -> 500.
    # Month 3: profit 300 all shielded (loss 200 left); month 4: 200 shielded + 100 x
    # 0.75; months 5-12: 300 x 0.75 = 225 each. 300 + 275 + 8 x 225 = 2375.
    table = projection.company_portfolio(_company(finances.property), "low", 1)
    assert table["year"].tolist() == [0.0, 1.0]
    assert table["value"].tolist() == pytest.approx([0.0, 2375.0])


def test_loss_used_after(finances: Finances) -> None:
    assert projection.loss_used_after(_company(finances.property), "low", 1) == 4 / 12


def test_loss_used_after_not_within_the_years_is_nan(finances: Finances) -> None:
    holding = _company(finances.property, assessed_loss=1_000_000.0)
    assert math.isnan(projection.loss_used_after(holding, "low", 1))


def test_loss_used_after_without_an_assessed_loss_is_0(finances: Finances) -> None:
    assert projection.loss_used_after(finances.property, "low", 1) == 0.0
    # No loss at the start and none from the bond months: rent paid 100 covers the 100
    # of levies and rates at 0% interest.
    covered = _company(finances.property, assessed_loss=0.0)
    covered = replace(covered, monthly={**covered.monthly, "rent_paid": 100.0})
    assert projection.loss_used_after(covered, "low", 1) == 0.0


def test_loss_used_after_counts_the_losses_of_the_bond_months(
    finances: Finances,
) -> None:
    # No loss at the start, but months 1-2 (bond) each add 100 (no rent paid, 100 of
    # costs): 200, used up by month 3's profit of 300, so 3 / 12 years.
    no_start = _company(finances.property, assessed_loss=0.0)
    assert projection.loss_used_after(no_start, "low", 1) == pytest.approx(0.25)


def test_company_portfolio_rent_grows_from_the_month_after_the_bond(
    finances: Finances,
) -> None:
    # No tax, no costs: month m >= 3 adds 400 x 1.44^((m - 3) / 12).
    holding = _company(
        finances.property, expenses=0.0, company_tax=0.0, rent_growth={"up": 0.44}
    )
    table = projection.company_portfolio(holding, "up", 2)
    first = sum(400 * 1.44 ** ((m - 3) / 12) for m in range(3, 13))
    both = sum(400 * 1.44 ** ((m - 3) / 12) for m in range(3, 25))
    assert table["value"].tolist() == pytest.approx([0.0, first, both])


def test_company_portfolio_phased_follows_the_person(finances: Finances) -> None:
    # Bond 0: month 1 counts as the bond's month, then 100 a month for months 2-12.
    holding = replace(
        _company(
            finances.property,
            rent=100.0,
            expenses=0.0,
            company_tax=0.0,
            portfolio_growth=0.5,
            phased=True,
        ),
        bond=0.0,
    )
    person = Person(
        age=60, retirement_age=62, inflation=0.0, phases=[Phase("a", 61, 0.0)]
    )
    with_person = projection.company_portfolio(holding, "low", 1, person)
    assert with_person["value"].iloc[-1] == pytest.approx(1100.0)
    alone = projection.company_portfolio(holding, "low", 1)
    expected = sum(100 * 1.5 ** (k / 12) for k in range(11))
    assert alone["value"].iloc[-1] == pytest.approx(expected)


def test_company_portfolio_zero_without_a_plan_or_before_the_bond_is_repaid(
    finances: Finances,
) -> None:
    none = projection.company_portfolio(finances.property, "low", 2)
    assert none["value"].tolist() == [0.0, 0.0, 0.0]
    running = replace(_company(finances.property), bond=18000.0)
    assert projection.company_portfolio(running, "low", 1)["value"].tolist() == [
        0.0,
        0.0,
    ]


def test_company_portfolio_unknown_scenario_raises(finances: Finances) -> None:
    with pytest.raises(KeyError):
        projection.company_portfolio(_company(finances.property), "missing", 1)


def test_projections_do_not_mutate_the_finances(finances: Finances) -> None:
    before = repr(finances)
    projection.net_worth(finances, USD_RATE)
    projection.allocation(finances)
    projection.retirement_table(finances, USD_RATE)
    assert repr(finances) == before
    assert isinstance(projection.listed_projection(finances, USD_RATE, 1), pd.DataFrame)
