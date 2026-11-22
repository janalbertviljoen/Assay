"""The private input turned into typed records (financial_planning/finances.py)."""

import datetime
from typing import Any

import pytest

from Toolbox.financial_planning.finances import Person, Phase, parse_finances


def test_parse_finances_accounts_with_defaults(raw: dict[str, Any]) -> None:
    finances = parse_finances(raw)
    fund_a, fund_b, pension = finances.accounts
    assert finances.as_of == datetime.date(2026, 11, 1)
    assert (fund_a.name, fund_a.kind, fund_a.currency) == ("Fund A", "listed", "ZAR")
    assert (fund_a.monthly, fund_a.growth, fund_a.escalation) == (100.0, 0.0, 0.0)
    assert fund_a.raises == {}
    assert fund_a.phased is False
    assert fund_a.source == ""
    assert fund_b.currency == "USD"
    assert (pension.kind, pension.growth) == ("retirement", 0.1)


def test_parse_finances_raises_are_keyed_by_year(raw: dict[str, Any]) -> None:
    raw["accounts"][0] |= {"raises": {"3": 0.2, "5": 0.1}, "phased": True}
    account = parse_finances(raw).accounts[0]
    assert account.raises == {3: 0.2, 5: 0.1}
    assert account.phased is True


def test_parse_finances_unknown_account_kind_raises(raw: dict[str, Any]) -> None:
    raw["accounts"][0]["kind"] = "crypto"
    with pytest.raises(ValueError, match="unknown kind 'crypto'"):
        parse_finances(raw)


def test_parse_finances_property_car_person_tfsa_and_buy_list(
    raw: dict[str, Any],
) -> None:
    finances = parse_finances(raw)
    holding = finances.property
    assert holding.name == "PropCo"
    assert holding.horizons == [1]
    assert holding.growth == {"low": 0.0, "high": 0.1}
    assert holding.monthly["paid_by_user"] == 1100.0
    assert holding.after_bond is None
    assert finances.targets == {"X": 30.0, "Y": 30.0, "Z": 20.0}
    assert finances.car is not None
    assert finances.car.loan == 1800.0
    assert finances.person == Person(
        age=60, retirement_age=62, inflation=0.1, phases=[]
    )
    assert finances.tfsa is not None
    assert finances.tfsa.annual_limit == 36000.0
    assert finances.buy_list == {
        "currency": "ZAR",
        "picks_amount": 5000.0,
        "fixed": {"NVX": 1000.0},
    }


def test_parse_finances_optional_parts_may_be_left_out(raw: dict[str, Any]) -> None:
    for key in ("car", "person", "tfsa", "buy_list"):
        del raw[key]
    finances = parse_finances(raw)
    assert finances.car is None
    assert finances.person is None
    assert finances.tfsa is None
    assert finances.buy_list == {}


def test_parse_finances_as_of_from_text(raw: dict[str, Any]) -> None:
    raw["as_of"] = "2026-10-31"
    assert parse_finances(raw).as_of == datetime.date(2026, 10, 31)


def test_parse_finances_missing_required_field_raises(raw: dict[str, Any]) -> None:
    del raw["property"]["bond"]
    with pytest.raises(KeyError):
        parse_finances(raw)


def test_parse_finances_after_bond_and_phases(raw: dict[str, Any]) -> None:
    raw["property"]["after_bond"] = {
        "rent": 400.0,
        "expenses": 100.0,
        "expense_growth": 0.05,
        "portfolio_growth": 0.08,
        "company_tax": 0.27,
        "assessed_loss": 300.0,
        "rent_growth": {"low": 0.0, "high": 0.06},
    }
    raw["person"]["phases"] = [
        {"name": "growth", "until_age": 61, "growth": 0.2},
        {"name": "defensive", "until_age": 70, "growth": 0.05},
    ]
    finances = parse_finances(raw)
    after = finances.property.after_bond
    assert after is not None
    assert (after.rent, after.assessed_loss, after.phased) == (400.0, 300.0, False)
    assert after.rent_growth == {"low": 0.0, "high": 0.06}
    assert finances.person is not None
    assert finances.person.phases == [
        Phase(name="growth", until_age=61, growth=0.2),
        Phase(name="defensive", until_age=70, growth=0.05),
    ]


@pytest.mark.parametrize(
    ("year", "expected"),
    [
        (0, 0.2),  # age 60
        (1, 0.05),  # age 61: exactly the first until_age moves to the next phase
        (9, 0.05),  # age 69
        (10, 0.01),  # age 70: past the last phase, the default
    ],
)
def test_person_growth_in_year(year: int, expected: float) -> None:
    person = Person(
        age=60,
        retirement_age=65,
        inflation=0.05,
        phases=[Phase("growth", 61, 0.2), Phase("defensive", 70, 0.05)],
    )
    assert person.growth_in_year(year, 0.01) == expected


def test_person_without_phases_uses_the_default() -> None:
    assert (
        Person(age=40, retirement_age=65, inflation=0.05).growth_in_year(0, 0.07)
        == 0.07
    )
