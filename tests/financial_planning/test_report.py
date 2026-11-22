"""The personal report's facts, tables and LaTeX (financial_planning/report.py)."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from tests.financial_planning.synthetic import make_buy_report, value_text
from Toolbox.financial_planning import report
from Toolbox.financial_planning.finances import (
    AfterBond,
    Finances,
    Phase,
    parse_finances,
)

USD_RATE = 20.0


@pytest.fixture
def finances(raw: dict[str, Any]) -> Finances:
    return parse_finances(raw)


def _inputs(finances: Finances, folder: Path) -> report.PersonalReport:
    return report.PersonalReport(
        finances, make_buy_report(folder), USD_RATE, folder / "property.png"
    )


def _with_company(finances: Finances) -> Finances:
    plan = AfterBond(
        rent=400.0,
        expenses=100.0,
        expense_growth=0.0,
        portfolio_growth=0.0,
        company_tax=0.25,
        assessed_loss=300.0,
        rent_growth={"low": 0.0, "high": 0.0},
    )
    return replace(finances, property=replace(finances.property, after_bond=plan))


@pytest.mark.parametrize(
    ("value", "text"),
    [(1234.4, "R1,234"), (0.0, "R0"), (-1500.0, "-R1,500")],
)
def test_rand_puts_the_sign_first(value: float, text: str) -> None:
    assert report._rand(value) == text


def test_personal_facts(finances: Finances, tmp_path: Path) -> None:
    facts = report.personal_facts(_inputs(finances, tmp_path))
    expected = {
        "net_worth": "R8,700",
        "listed": "R3,000",
        "retirement": "R3,000",
        "property_stake": "R2,500",
        "property_share": "29%",
        "property_name": "PropCo",
        "property_value": "R20,000",
        "bond": "R18,000",
        "bond_note": "a synthetic bond",
        "rate": "0.0%",
        "into_bond": "R1,000",
        "extra": "R400",
        "repaid_years": "1.5",
        "largest_overweight": "X",
        "largest_overweight_gap": "+12.5",
        "largest_underweight": "Y",
        "largest_underweight_gap": "-7.5",
        "horizon_end": "1",
        "members_loan": "R4,000",
        "property_cost": "R15,000",
        "usd_rate": "20.00",
        "car_loan": "R1,800",
        "car_repaid_years": "0.3",
        # The scenarios by position, never by their rate.
        "scenario_1": "low",
        "growth_1": "0%",
        "equity_end_1": "R14,000",
        "scenario_2": "high",
        "growth_2": "10%",
        "equity_end_2": "R16,000",
        # The pension at 10% for the horizons (1 year): 3000 x 1.1.
        "retirement_growth": "10%",
        "horizon_1": "1",
        "retirement_h1": "R3,300",
        "age": "60",
        "years_to_retire": "2",
        "inflation": "10%",
        "total_end_1": "R29,030",
        "total_end_2": "R33,230",
        "real_end_1": "R23,992",
        "real_end_2": "R27,463",
        "company_end_1": "R0",
        "listed_end": "R5,400",
        "listed_monthly": "R100",
        "tfsa_room": "R400,000",
        "tfsa_full_years": "333",
    }
    assert {k: facts[k] for k in expected} == expected
    assert "phases" not in facts
    assert "loss_used_1" not in facts


def test_personal_facts_keys_do_not_depend_on_the_rates(
    finances: Finances, tmp_path: Path
) -> None:
    changed = replace(
        finances,
        property=replace(finances.property, growth={"low": 0.03, "high": 0.07}),
    )
    before = report.personal_facts(_inputs(finances, tmp_path))
    after = report.personal_facts(_inputs(changed, tmp_path))
    assert set(before) == set(after)


def test_personal_facts_of_the_company_and_the_phases(
    finances: Finances, tmp_path: Path
) -> None:
    person = replace(
        finances.person, phases=[Phase("growth", 61, 0.2), Phase("defensive", 70, 0.05)]
    )
    facts = report.personal_facts(
        _inputs(replace(_with_company(finances), person=person), tmp_path)
    )
    assert facts["phases"] == "20% until 61 and 5% until 70"
    assert facts["assessed_loss"] == "R300"
    assert facts["company_tax"] == "25%"
    assert facts["rent_paid"] == "R0"
    assert {
        "loss_used_1",
        "loss_used_2",
        "company_end_1",
        "company_end_2",
        "after_rent",
        "after_expenses",
    } <= set(facts)


def test_personal_facts_without_car_person_or_tfsa(
    finances: Finances, tmp_path: Path
) -> None:
    bare = replace(finances, car=None, person=None, tfsa=None)
    facts = report.personal_facts(_inputs(bare, tmp_path))
    assert not {"car_loan", "age", "total_end_1", "tfsa_room"} & set(facts)
    assert facts["net_worth"] == "R8,500"


# Every placeholder the personal report fills, with the value report's.
PLACEHOLDERS = [
    "net_worth",
    "listed",
    "retirement",
    "property_stake",
    "property_share",
    "property_name",
    "property_value",
    "bond",
    "bond_note",
    "rate",
    "into_bond",
    "extra",
    "repaid_years",
    "largest_overweight",
    "largest_overweight_gap",
    "largest_underweight",
    "largest_underweight_gap",
    "horizon_end",
    "members_loan",
    "property_cost",
    "usd_rate",
    "car_value",
    "car_loan",
    "car_rate",
    "car_payment",
    "car_insurance",
    "car_repaid_years",
    "phases",
    "retirement_growth",
    "retirement_monthly",
    "retirement_escalation",
    "horizon_1",
    "retirement_h1",
    "age",
    "retirement_age",
    "years_to_retire",
    "inflation",
    "total_end_1",
    "total_end_2",
    "real_end_1",
    "real_end_2",
    "company_end_1",
    "company_end_2",
    "after_rent",
    "after_expenses",
    "assessed_loss",
    "rent_paid",
    "company_tax",
    "loss_used_1",
    "loss_used_2",
    "listed_end",
    "listed_monthly",
    "tfsa_room",
    "tfsa_full_years",
    "scenario_1",
    "scenario_2",
    "growth_1",
    "growth_2",
    "equity_end_1",
    "equity_end_2",
    "buy_total",
    "currency",
    "picks",
]


def _text() -> dict[str, Any]:
    every = " ".join(f"{{{k}}}" for k in PLACEHOLDERS)
    return {
        "title": "Personal report",
        "abstract": "Net worth {net_worth}.",
        "portfolio": {
            "title": "Portfolio",
            "text": every,
            "worth_caption": "Worth",
            "allocation_title": "Allocation",
            "allocation_text": "Over {largest_overweight}.",
            "allocation_caption": "Allocation",
        },
        "property": {
            "title": "{property_name}",
            "text": "Bond {bond}.",
            "cash_caption": "Cash",
            "projection_title": "Projection",
            "projection_text": "{scenario_1} and {scenario_2}.",
            "projection_caption": "Projection",
            "figure": "Paths",
        },
        "retirement": {
            "title": "Retirement",
            "text": "At {retirement_age}.",
            "caption": "R",
        },
    }


def test_build_personal_report_resolves_every_placeholder_in_its_folder(
    finances: Finances, tmp_path: Path
) -> None:
    person = replace(
        finances.person, phases=[Phase("a", 61, 0.2), Phase("b", 70, 0.05)]
    )
    full = replace(_with_company(finances), person=person)
    folder = tmp_path / "build"
    tex = report.build_personal_report(
        _inputs(full, tmp_path),
        _text(),
        value_text(),
        folder=folder,
        subtitle="private",
    )
    assert tex == folder / "personal_report.tex"
    files = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    assert files == ["build", "build/personal_report.tex"]
    latex = tex.read_text()
    assert "R8,700" in latex
    for label in ("tab:worth", "tab:allocation", "tab:cash", "tab:projection"):
        assert label in latex
    for label in ("tab:retirement", "tab:next", "tab:buy-list", "tab:trends"):
        assert label in latex


def test_build_personal_report_unknown_placeholder_raises(
    finances: Finances, tmp_path: Path
) -> None:
    text = _text()
    text["abstract"] = "{no_such_fact}"
    with pytest.raises(KeyError):
        report.build_personal_report(
            _inputs(finances, tmp_path),
            text,
            value_text(),
            folder=tmp_path,
            subtitle="",
        )


def test_build_personal_report_leaves_out_retirement_without_the_person(
    finances: Finances, tmp_path: Path
) -> None:
    text = _text()
    text["portfolio"]["text"] = "{net_worth}"
    text["retirement"]["text"] = "{retirement_age}"  # not read without a person
    tex = report.build_personal_report(
        _inputs(replace(finances, person=None), tmp_path),
        text,
        value_text(),
        folder=tmp_path,
        subtitle="",
    )
    assert "tab:retirement" not in tex.read_text()


def test_personal_facts_of_one_phase(finances: Finances, tmp_path: Path) -> None:
    person = replace(finances.person, phases=[Phase("growth", 61, 0.2)])
    facts = report.personal_facts(_inputs(replace(finances, person=person), tmp_path))
    assert facts["phases"] == "20% until 61"
