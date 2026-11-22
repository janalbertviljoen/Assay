"""
financial_planning/plots.py
----------------
The personal report's figure: the property's value, bond and equity over the years,
one line style per growth scenario.

Owns
----
The title, axes and layout of the property projection figure.

Must not
--------
Project (``financial_planning.projection``); save files (``financial_planning.__main__``).

Public API
----------
property_paths(projections, savings, *, start_age)
    Value and equity per scenario, the bond, and the savings accounts, over the years.

Dependency rule
---------------
pandas and matplotlib.
"""

# matplotlib annotates its plotting methods with untyped **kwargs, which strict pyright
# reports on every call; the arguments passed here are all typed.
# pyright: reportUnknownMemberType=false

from collections.abc import Mapping

import pandas as pd
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

STYLES = ("-", "--", ":", "-.")


def _millions(value: float, _position: int | None = None) -> str:
    """Return an axis value in millions of rand (``R1.5m``)."""
    return f"R{value / 1e6:.1f}m"


def property_paths(
    projections: Mapping[str, pd.DataFrame],
    savings: Mapping[str, pd.DataFrame],
    *,
    start_age: int,
) -> Figure:
    """Plot the property's value and equity per scenario, the bond and the savings.

    ``projections`` maps a scenario's name to ``financial_planning.projection.property_projection``
    output; the bond is the same in every scenario and drawn once. ``savings`` maps a
    label to a ``year``/``value`` projection, drawn in purple and orange. The x axis is
    the founder's age, ``start_age`` today.
    """
    figure = Figure(figsize=(9, 4.2))
    axis = figure.subplots()
    first = next(iter(projections.values()))
    for (name, table), style in zip(projections.items(), STYLES, strict=False):
        axis.plot(
            start_age + table["year"],
            table["value"],
            color="tab:blue",
            ls=style,
            label=f"value, {name}",
        )
        axis.plot(
            start_age + table["year"],
            table["equity"],
            color="tab:green",
            ls=style,
            label=f"equity, {name}",
        )
    axis.plot(start_age + first["year"], first["bond"], color="tab:red", label="bond")
    for (label, table), colour in zip(
        savings.items(), ("tab:purple", "tab:orange"), strict=False
    ):
        axis.plot(start_age + table["year"], table["value"], color=colour, label=label)
    axis.yaxis.set_major_formatter(FuncFormatter(_millions))
    axis.set_xlabel("age")
    axis.grid(alpha=0.3)
    axis.legend(fontsize=8, loc="upper left")
    figure.tight_layout()
    return figure
