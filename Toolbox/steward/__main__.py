r"""
steward/__main__.py
-------------------
The terminal command that writes the founder's personal report.

Run from the repository root, after the value tool has scored the as-of date::

    .venv/bin/python -m Toolbox.value_investing buyability --as-of 2026-11-19 --no-plots
    .venv/bin/python -m Toolbox.steward report --as-of 2026-11-19

It reads the private finances (``finances.toml``) and the report's text
(``report_text.toml``) from the private workspace ``--private-dir`` (default
``../Personal/Finances``: ``~/Documents/Personal/Finances/``, the private repository
beside this public one), the value tool's picks and buy list for the index
(``value_investing.io.buy_report_inputs``, with the private amounts), builds the figures
and the LaTeX in a temporary folder there, and keeps only
``<private-dir>/reports/<as_of>/personal_report.pdf``. Nothing private is written inside
this repository.

Owns
----
The command-line interface and the private report's location.

Must not
--------
Project, summarise or format (``steward.projection``, ``steward.report``); write
anywhere but the private workspace.

Public API
----------
main(argv)
    Run the ``report`` command; returns the exit code.

Dependency rule
---------------
The standard library, ``skatkis.io``, ``skatkis.report``, ``steward`` and
``value_investing``.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from Toolbox.skatkis.io.config import load_config
from Toolbox.skatkis.io.figures import save_figure
from Toolbox.skatkis.report import compile_pdf
from Toolbox.steward import plots, projection, report
from Toolbox.steward.finances import parse_finances
from Toolbox.value_investing.io import buy_report_inputs

LATEX_ENGINE = "tectonic"


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``report`` command."""
    args = _parser().parse_args(argv)
    return _report(args)


def _report(args: argparse.Namespace) -> int:
    """Write the personal report and keep only its PDF in the private workspace."""
    private: Path = args.private_dir
    finances = parse_finances(load_config(args.finances or private / "finances.toml"))
    rules = load_config(args.rules)
    target = private / "reports" / args.as_of.isoformat()
    target.mkdir(parents=True, exist_ok=True)
    # The build (figures, LaTeX) stays in the private workspace, removed afterwards.
    with tempfile.TemporaryDirectory(dir=target) as build:
        folder = Path(build)
        buy = buy_report_inputs(
            as_of=args.as_of,
            rules=rules,
            index=args.index,
            data_dir=args.data_dir,
            indices=args.indices,
            report_text=args.value_text,
            folder=folder,
            amounts=finances.buy_list,
        )
        usd_rate = float(buy.buy.settings["rate"])
        holding = finances.property
        figure = save_figure(
            plots.property_paths(
                {
                    name: projection.property_projection(holding, growth)
                    for name, growth in holding.growth.items()
                },
                {
                    **{
                        f"{a.name} at {a.growth:.0%}": projection.savings_projection(
                            a, holding.years, finances.person
                        )
                        for a in finances.accounts
                        if a.kind == "retirement" and a.growth > 0
                    },
                    "Listed funds by risk phase, with the TFSA contributions": (
                        projection.listed_projection(finances, usd_rate, holding.years)
                    ),
                },
                start_age=finances.person.age if finances.person else 0,
            ),
            folder / "property.png",
        )
        tex = report.build_personal_report(
            report.PersonalReport(finances, buy, usd_rate, figure),
            load_config(args.text or private / "report_text.toml"),
            load_config(args.value_text),
            folder=folder,
            subtitle=(
                f"Prices as of {args.as_of.isoformat()}; finances as of "
                f"{finances.as_of.isoformat()}; private"
            ),
        )
        engine = shutil.which(LATEX_ENGINE)
        if engine is None:
            print(f"{LATEX_ENGINE} not found: {tex} not compiled.")
            return 1
        try:
            pdf = compile_pdf(
                tex, engine=engine, cache=args.data_dir / "cache" / "tectonic"
            )
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or b"").decode(errors="replace").splitlines()[-3:]
            print(f"LaTeX failed: {' '.join(detail)}")
            return 1
        shutil.copyfile(pdf, target / "personal_report.pdf")
    print(f"Personal report: {target / 'personal_report.pdf'}")
    return 0


def _parser() -> argparse.ArgumentParser:
    """Return the argument parser."""
    parser = argparse.ArgumentParser(prog="python -m Toolbox.steward")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("report", help="write the personal report (PDF)")
    command.add_argument("--as-of", type=date.fromisoformat, required=True)
    command.add_argument("--index", default="sp500")
    command.add_argument("--data-dir", type=Path, default=Path("data"))
    command.add_argument(
        "--private-dir",
        type=Path,
        default=Path("../Personal/Finances"),
        help="the private workspace (the private repository's Finances/)",
    )
    command.add_argument(
        "--finances",
        type=Path,
        default=None,
        help="default: <private-dir>/finances.toml",
    )
    command.add_argument("--rules", type=Path, default=Path("config/rules.toml"))
    command.add_argument("--indices", type=Path, default=Path("config/indices.toml"))
    command.add_argument(
        "--text",
        type=Path,
        default=None,
        help="default: <private-dir>/report_text.toml",
    )
    command.add_argument(
        "--value-text", type=Path, default=Path("config/report_value_investing.toml")
    )
    return parser


if __name__ == "__main__":
    sys.exit(main())
