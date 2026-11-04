"""
value_investing/report.py
-------------------------
Assembles the value-investing report: buy-and-hold results with the report's text.

The text (title, abstract, section texts and captions) is in
``config/report_value_investing.toml``, which the Scribe writes; this module fills
its placeholders from the results, builds the tables (picks, wallets, sales, next
picks, the worst list of the lowest scores, and the static tables of the missed
winners, the testing, and the reading list) and the appendix of every
purchase, and places the figures. ``skatkis.report`` writes the LaTeX document.

Owns
----
The facts the text refers to, the tables of the report and the order of its sections.

Must not
--------
Compute holdings or returns (``value_investing.holding``); plot
(``value_investing.plots``); write the text (``config/report_value_investing.toml``).

Public API
----------
Peers(label, ranks, profile, summary)
    A peer group set against the picks.
ReportInputs(held, managed, next_picks, worst, profile, weighting, peers, names, ...)
    What the report shows.
report_facts(inputs)
    The values of the text's placeholders.
build_report(inputs, text, *, folder, subtitle)
    Write ``report.tex`` and return its path.

Dependency rule
---------------
pandas, ``skatkis.report`` and ``value_investing.holding``.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pandas as pd

from Toolbox.skatkis.report import (
    Document,
    FigureGroup,
    ReportFigure,
    Section,
    Table,
    write_latex,
)
from Toolbox.value_investing.holding import (
    MANAGED,
    WALLET,
    BuyAndHold,
    Managed,
    dollar_view,
    weighting_quality,
)
from Toolbox.value_investing.rules import RULES

SCORE_LABELS = {
    "score_binned_weighted": "Score",
    "score_weighted_share": "Score 0 to 1",
    "score_binned": "Unweighted",
    "score": "Share passed",
}
MAX_PANELS_IN_ROW = 3  # more start years than this are laid out two by two
TOP_PICKS = 5  # the largest wins named in the text
HALF_CENT = 0.005  # holdings below half a cent are left blank in the tables
# Placeholder prefixes and table labels per holder; the index's benchmark (the first
# comparison) is ``sp`` in the text and named by the index's label.
NAMES = {WALLET: "wallet", MANAGED: "managed", "BRK-B": "brk"}
LABELS = {
    WALLET: "Value wallet",
    MANAGED: "Value wallet with sells",
    "BRK-B": "Berkshire Hathaway",
}


@dataclass(frozen=True)
class Peers:
    """A peer group set against the picks (``value_investing.peers``).

    Parameters
    ----------
    label : str
        The group's name in the text, e.g. ``Magnificent 7``.
    ranks : pd.DataFrame
        ``peers.peer_ranks`` output.
    profile : pd.DataFrame
        ``peers.peer_profile`` output.
    summary : pd.DataFrame
        ``BuyAndHold.summary`` of the same money in the group, equal weights.
    """

    label: str
    ranks: pd.DataFrame
    profile: pd.DataFrame
    summary: pd.DataFrame


@dataclass(frozen=True)
class ReportInputs:
    """What the report shows.

    Parameters
    ----------
    held : BuyAndHold
        Lots, yearly purchases, value paths and summary.
    managed : Managed
        The wallet that also sells: trades, summary and current holdings.
    next_picks : pd.DataFrame
        The picks on the latest score date: ``symbol``, ``gics_sector``, ``score``,
        ``score_share``, ``weight``, ``score_date``.
    worst : pd.DataFrame
        The lowest scores of the scored companies of the index on the latest score date
        (Financials, Real Estate and companies with too few rules are not scored),
        whatever anyone holds, as many as the picks, ties broken by symbol:
        ``symbol``, ``gics_sector``, ``score``, ``score_share``, ``score_date``, plus the
        ranked-position columns ``decision_date``, ``side``, ``weight`` and ``amount``
        (of a hypothetical sell book, not a recommendation) and ``date``.
    profile : pd.DataFrame
        ``value_investing.holding.rule_profile`` output.
    weighting : pd.DataFrame
        ``value_investing.holding.rule_weighting`` output.
    peers : Peers or None
        The peer group compared with the picks; None when no company of the group is
        in the index, and the peer section is then left out.
    lookahead : pd.DataFrame
        ``value_investing.lookahead.truncation_check`` output.
    survivorship : pd.DataFrame
        Per start year: ``start``, ``removed`` (companies that left the S&P 500 since
        then, all missing from the data) and ``market_cap`` (of those, removed for their
        market value, the likely losers).
    reference : int
        The start year of the investor the abstract, the conclusions and the detailed
        views follow: a recent one, so fewer failed companies are missing.
    names : Mapping[str, str]
        Each company's full name by symbol, for the concluding parts.
    index_label : str
        The index's name (``S&P MidCap 400``), the ``{index}`` of the text.
    benchmark_name : str
        How the text names the benchmark (``{benchmark_name}``).
    membership : str
        The text's note on how membership dates are known (``{membership}``).
    record_start : pd.Timestamp
        The first date of the index's list of changes (``{record_start}``).
    pick_scenario, pick_years, pick_ends : int
        The price-history settings (``[report]``), named in the text.
    rules : Mapping[str, Mapping[str, Any]]
        Each rule's thresholds (``[rules.<ID>]``, with ``[valuation]`` merged in), to
        fill the rule descriptions.
    figures : Mapping[str, Path]
        Saved figures: ``yearly``, ``rules``, ``weighting``, ``contents``,
        ``pick_prices``, ``trade_amounts``, ``next_prices``, ``worst_prices``, ``peers``
        (when there is a peer group) and ``value_<start year>`` per scenario.
    compare : Sequence[str]
        The comparisons: the index's benchmark first, then ``BRK-B``.
    amount : float
        USD invested per decision.
    picks : int
        Companies bought per decision.
    end : pd.Timestamp
        Valuation date.
    threshold : float
        Score share at or below which a holding is sold in part.
    tier_cutoffs : Sequence[float]
        The 0-to-1 scores above which a score is Green, Amber and Red; at or below the
        last it is Black (``[report] tier_cutoffs``).
    verdict_band : float
        The weight-gap rank correlation above which the weighting favours the rules
        that told winners from losers, and below minus which it favours the wrong ones.
    static_note : str
        A notice put before the section that states figures written out in the text,
        when they were produced with another model configuration or data date; empty
        when they match.
    stress : pd.DataFrame, optional
        ``holding.winner_stress`` output; the testing section's winners-removed
        subsection is left out when missing.
    ranking : pd.DataFrame, optional
        ``rank``, ``symbol``, ``gics_sector``, ``score``, ``score_share`` of every
        scored company on the latest score date (``evaluation.ranking`` with the sector
        and the 0-to-1 score); the appendix listing it is left out when missing.
    """

    held: BuyAndHold
    managed: Managed
    next_picks: pd.DataFrame
    worst: pd.DataFrame
    profile: pd.DataFrame
    weighting: pd.DataFrame
    peers: Peers | None
    lookahead: pd.DataFrame
    survivorship: pd.DataFrame
    names: Mapping[str, str]
    index_label: str
    benchmark_name: str
    membership: str
    record_start: pd.Timestamp
    pick_scenario: int
    pick_years: int
    pick_ends: int
    reference: int
    rules: Mapping[str, Mapping[str, Any]]
    figures: Mapping[str, Path]
    compare: Sequence[str]
    amount: float
    picks: int
    end: pd.Timestamp
    threshold: float
    tier_cutoffs: Sequence[float]
    verdict_band: float
    static_note: str = ""
    stress: pd.DataFrame | None = None
    ranking: pd.DataFrame | None = None


def report_facts(inputs: ReportInputs, names: Mapping[str, str]) -> dict[str, str]:
    """Return the values of the text's placeholders, formatted for reading.

    ``names`` gives each rule ID its name in the text (``[rule_names]``).
    """
    held = inputs.held
    years = held.yearly["decision_date"].dt.year
    facts: dict[str, str] = {
        "end": f"{inputs.end:%d %B %Y}",
        "first_year": str(int(years.min())),
        "last_year": str(int(years.max())),
        "picks": str(inputs.picks),
        "amount": f"{inputs.amount:,.0f}",
        "index": inputs.index_label,
        "benchmark_name": inputs.benchmark_name,
        "record_start": f"{inputs.record_start:%B %Y}",
        "pick_scenario": str(inputs.pick_scenario),
        "pick_years": str(inputs.pick_years),
        "pick_ends": str(inputs.pick_ends),
    }
    facts["membership"] = inputs.membership.format(record_start=facts["record_start"])
    summary = pd.concat([held.summary, inputs.managed.summary], ignore_index=True)
    for row in summary.to_dict("records"):
        name = {**NAMES, inputs.compare[0]: "sp"}.get(
            str(row["holder"]), str(row["holder"]).lower()
        )
        start = int(row["scenario"])
        facts[f"invested_{start}"] = f"{float(row['invested_usd']):,.0f}"
        facts[f"{name}_{start}"] = f"{float(row['value_usd']):,.0f}"
        facts[f"{name}_rate_{start}"] = f"{float(row['annual_return']):.1%}"
    lots = held.lots.assign(multiple=1 + held.lots["total_return"])
    best = lots.sort_values("multiple", ascending=False).iloc[0]
    reference = held.summary[
        (held.summary["holder"] == WALLET)
        & (held.summary["scenario"] == inputs.reference)
    ]
    first = float(reference["value_usd"].iloc[0])
    later = pd.DatetimeIndex(lots["decision_date"]).year >= inputs.reference
    own_lots = lots.loc[pd.Series(later, index=lots.index)]
    by_company = (
        own_lots.groupby("symbol")["value_usd"].sum().sort_values(ascending=False)
    )
    sectors = lots.groupby("gics_sector")["invested_usd"].sum()
    facts["top_sectors"] = _listing(
        [str(s) for s in sectors.sort_values(ascending=False).index[:3]]
    )
    facts["best_pick"] = str(best["symbol"])
    facts["best_year"] = f"{pd.Timestamp(best['decision_date']):%B %Y}"
    facts["best_multiple"] = f"{float(best['multiple']):.0f}"
    facts["best_company"] = _full(inputs, str(by_company.index[0]))
    facts["best_company_buys"] = str(
        int((own_lots["symbol"] == by_company.index[0]).sum())
    )
    facts["best_company_share"] = f"{float(by_company.iloc[0]) / first:.0%}"
    beat = held.lots["annualised_excess"] > 0
    facts["winners"] = str(int(beat.sum()))
    facts["losers"] = str(int((~beat).sum()))
    gap = inputs.profile.pivot_table(index="rule", columns="group", values="points")
    difference = (gap["beat the index"] - gap["did not"]).sort_values()
    facts["winner_rules"] = _listing(
        [_named(r, names) for r in difference.index[::-1][:4]]
    )
    facts["loser_rules"] = _listing([_named(r, names) for r in difference.index[:2]])
    trailing = held.yearly[
        held.yearly["value_usd"] < held.yearly[f"{inputs.compare[0]}_usd"]
    ]
    facts["loss_years"] = _listing([f"{d:%B %Y}" for d in trailing["decision_date"]])
    facts.update(_wallet_facts(inputs))
    facts.update(_dollar_facts(inputs))
    facts.update(_weighting_facts(inputs, names))
    if inputs.peers is not None:
        facts.update(_peer_facts(inputs, inputs.peers, names))
    facts.update(_lookahead_facts(inputs))
    facts.update(_stress_facts(inputs))
    reference = str(inputs.reference)
    facts["ref_start"] = reference
    for key in [k for k in list(facts) if k.endswith(f"_{reference}")]:
        facts["ref_" + key.removesuffix(f"_{reference}")] = facts[key]
    removed = inputs.survivorship.set_index("start")["removed"]
    facts["ref_removed"] = str(int(removed.get(inputs.reference, 0)))
    facts["first_removed"] = str(int(removed.iloc[0]))
    facts["first_year_start"] = str(int(removed.index[0]))
    return facts


def _dollar_facts(inputs: ReportInputs) -> dict[str, str]:
    """Return the facts of the dollar view: totals, payoff ratio, the largest wins."""
    view = {
        str(r["group"]): r for r in dollar_view(inputs.held.lots).to_dict("records")
    }
    beat, lagged, every = view["beat"], view["lagged"], view["all"]
    lots = inputs.held.lots.sort_values("ahead_usd", ascending=False)
    top = lots.head(TOP_PICKS)
    won = float(beat["total_usd"])
    payoff = float(beat["mean_usd"]) / -float(lagged["mean_usd"])
    return {
        "winners_usd": f"{won:,.0f}",
        "losers_usd": f"{-float(lagged['total_usd']):,.0f}",
        "net_usd": f"{float(every['total_usd']):,.0f}",
        "winners_median": f"{float(beat['median_usd']):,.0f}",
        "losers_median": f"{-float(lagged['median_usd']):,.0f}",
        "payoff": f"{payoff:.1f}",
        "top_n": str(TOP_PICKS),
        "top_share": f"{float(top['ahead_usd'].sum()) / won:.0%}",
        "top_picks": _listing(
            [
                f"{symbol} {pd.Timestamp(day):%b %Y}"
                for symbol, day in zip(top["symbol"], top["decision_date"], strict=True)
            ]
        ),
    }


def _dollar_table(inputs: ReportInputs) -> Table:
    """Return the dollars ahead of the index of the winning and losing picks."""
    names = {
        "beat": f"Beat the {inputs.index_label}",
        "lagged": f"Lagged the {inputs.index_label}",
        "all": "All picks",
    }
    rows = [
        [
            names[str(r["group"])],
            str(int(r["picks"])),
            f"{float(r['total_usd']):+,.0f}",
            f"{float(r['mean_usd']):+,.1f}",
            f"{float(r['median_usd']):+,.1f}",
        ]
        for r in dollar_view(inputs.held.lots).to_dict("records")
    ]
    return Table(
        header=["Picks", "Number", "USD ahead, total", "Average", "Median"],
        rows=rows,
        columns="l r r r r",
        breaks=(1,),
    )


def _wallet_facts(inputs: ReportInputs) -> dict[str, str]:
    """Return the facts of the wallet with sells, next year's picks and the worst stocks."""
    first_start = inputs.reference
    trades = inputs.managed.trades
    sales = trades[(trades["scenario"] == first_start) & (trades["action"] == "sell")]
    picks = inputs.next_picks
    worst = inputs.worst
    return {
        "threshold": f"{inputs.threshold:g}",
        "first_start": str(first_start),
        "sales": str(len(sales)),
        "sold_usd": f"{float(sales['usd'].sum()):,.0f}",
        "next_score_date": f"{pd.Timestamp(picks['score_date'].iloc[0]):%d %B %Y}",
        "next_picks": _listing([_full(inputs, str(s)) for s in picks["symbol"]]),
        "tier_green": f"{inputs.tier_cutoffs[0]:g}",
        "tier_amber": f"{inputs.tier_cutoffs[1]:g}",
        "tier_red": f"{inputs.tier_cutoffs[2]:g}",
        "worst_count": str(len(worst)),
        "ranked_count": str(len(inputs.ranking)) if inputs.ranking is not None else "0",
        "worst_list": _listing([_full(inputs, str(s)) for s in worst["symbol"]]),
    }


def _full(inputs: ReportInputs, symbol: str) -> str:
    """Return ``Full Name (SYMBOL)``, or the symbol alone when the name is unknown."""
    name = inputs.names.get(symbol)
    return f"{name} ({symbol})" if name else symbol


def _peer_facts(
    inputs: ReportInputs, group: Peers, names: Mapping[str, str]
) -> dict[str, str]:
    """Return the facts of the peer comparison: ranks and the peer wallet's value."""
    ranks = group.ranks.dropna(subset=["rank"]).sort_values("rank")
    facts = {
        "peer_label": group.label,
        "peer_best": _full(inputs, str(ranks["symbol"].iloc[0])),
        "peer_best_rank": f"{float(ranks['rank'].iloc[0]):.0f}",
        "peer_worst": _full(inputs, str(ranks["symbol"].iloc[-1])),
        "peer_worst_rank": f"{float(ranks['rank'].iloc[-1]):.0f}",
        "peer_companies": f"{float(ranks['companies'].iloc[0]):.0f}",
    }
    gap = group.profile.pivot_table(index="rule", columns="group", values="points")
    order = (gap["picks"] - gap["peers"]).sort_values(ascending=False)
    facts["peer_behind"] = _listing([_named(str(r), names) for r in order.index[:4]])
    facts["peer_ahead"] = _listing(
        [_named(str(r), names) for r in order.index[::-1] if order[r] < 0][:3]
    )
    for row in group.summary.to_dict("records"):
        if str(row["holder"]) != WALLET:
            continue
        start = int(row["scenario"])
        facts[f"peer_{start}"] = f"{float(row['value_usd']):,.0f}"
        facts[f"peer_rate_{start}"] = f"{float(row['annual_return']):.1%}"
    return facts


def _weighting_facts(inputs: ReportInputs, names: Mapping[str, str]) -> dict[str, str]:
    """Return the facts of the weighting test."""
    check = inputs.weighting
    quality = weighting_quality(check)
    middle = float(check["weight"].median())
    heavy = check[(check["weight"] >= middle) & (check["gap"] < 0)]
    light = check[(check["weight"] < middle) & (check["gap"] > 0)]
    return {
        "quality_gap": f"{quality['weight_vs_gap']:+.2f}",
        "quality_ic": f"{quality['weight_vs_ic']:+.2f}",
        "overweighted": _listing([_named(str(r), names) for r in heavy["rule"]]),
        "underweighted": _listing([_named(str(r), names) for r in light["rule"]]),
        "picks_n": str(len(inputs.held.lots)),
    }


def build_report(
    inputs: ReportInputs, text: Mapping[str, Any], *, folder: Path, subtitle: str
) -> Path:
    """Write the report's LaTeX into ``folder`` and return the ``report.tex`` path.

    Parameters
    ----------
    inputs : ReportInputs
        Results and saved figures.
    text : Mapping[str, Any]
        The parsed ``config/report_value_investing.toml``.
    folder : Path
        Where ``report.tex`` is written, next to the figures.
    subtitle : str
        The line under the title, e.g. the data date.
    """
    facts = report_facts(inputs, text["rule_names"])

    def fill(value: object) -> str:
        return str(value).format(**facts)

    scenarios = sorted(int(s) for s in inputs.held.summary["scenario"].unique())
    sections = [
        Section(title=fill(text["method"]["title"]), text=fill(text["method"]["text"])),
        Section(
            title=fill(text["picks"]["title"]),
            text=fill(text["picks"]["text"]),
            table=replace(
                _picks_table(inputs),
                caption=fill(text["picks"]["table_caption"]),
                label="tab:picks",
            ),
            figures=[
                ReportFigure(
                    inputs.figures["yearly"],
                    fill(text["picks"]["figure"]),
                    label="fig:yearly",
                )
            ],
        ),
        Section(
            title=fill(text["value"]["title"]),
            text=fill(text["value"]["text"]),
            table=replace(
                _summary_table(inputs),
                caption=fill(text["value"]["table_caption"]),
                label="tab:value",
            ),
            figures=[
                FigureGroup(
                    panels=[
                        ReportFigure(inputs.figures[f"value_{s}"], f"From {s}")
                        for s in scenarios
                    ],
                    caption=fill(text["value"]["figure"]),
                    columns=2 if len(scenarios) > MAX_PANELS_IN_ROW else len(scenarios),
                    label="fig:value",
                )
            ],
        ),
        Section(
            title=fill(text["selling"]["title"]),
            text=fill(text["selling"]["text"]),
            subsections=[
                Section(
                    title=fill(text["selling"]["sold_title"]),
                    text=fill(text["selling"]["sold_text"]),
                    table=replace(
                        _sales_table(inputs),
                        caption=fill(text["selling"]["table_caption"]),
                        label="tab:sales",
                    ),
                ),
            ],
            label="sec:selling",
        ),
        Section(
            title=fill(text["contents"]["title"]),
            text=fill(text["contents"]["text"]),
            figures=[
                ReportFigure(
                    inputs.figures["contents"],
                    fill(text["contents"]["figure"]),
                    label="fig:contents",
                )
            ],
        ),
        Section(
            title=fill(text["rules"]["title"]),
            text=fill(text["rules"]["text"]),
            table=replace(
                _dollar_table(inputs),
                caption=fill(text["rules"]["table_caption"]),
                label="tab:dollars",
            ),
            figures=[
                ReportFigure(
                    inputs.figures["rules"],
                    fill(text["rules"]["figure"]),
                    label="fig:rules",
                )
            ],
        ),
        Section(
            title=fill(text["history"]["title"]),
            text=fill(text["history"]["text"]),
            figures=[
                ReportFigure(
                    inputs.figures["pick_prices"],
                    fill(text["history"]["prices_figure"]),
                    label="fig:pick-prices",
                ),
                ReportFigure(
                    inputs.figures["trade_amounts"],
                    fill(text["history"]["amounts_figure"]),
                    label="fig:trade-amounts",
                ),
            ],
        ),
        Section(
            title=fill(text["next"]["title"]),
            text=fill(text["next"]["text"]),
            table=replace(
                _next_table(inputs, text["sectors"]),
                caption=fill(text["next"]["table_caption"]),
                label="tab:next",
            ),
            figures=[
                ReportFigure(
                    inputs.figures["next_prices"],
                    fill(text["next"]["prices_figure"]),
                    label="fig:next-prices",
                )
            ],
        ),
        Section(
            title=fill(text["missed"]["title"]),
            text=fill(text["missed"]["text"]),
            table=_static_table(
                text["missed"]["table"],
                fill(text["missed"]["table_caption"]),
                "tab:missed",
            ),
            label="sec:missed",
        ),
        Section(
            title=fill(text["selling"]["worst_title"]),
            text=fill(text["selling"]["worst_text"]),
            table=replace(
                _worst_table(inputs),
                caption=fill(text["selling"]["worst_caption"]),
                label="tab:worst",
            ),
            figures=[
                ReportFigure(
                    inputs.figures["worst_prices"],
                    fill(text["selling"]["worst_figure"]),
                    label="fig:worst-prices",
                )
            ],
            label="sec:worst",
        ),
        Section(
            title=fill(text["testing"]["title"]),
            text=(
                (inputs.static_note + "\n\n" if inputs.static_note else "")
                + fill(text["testing"]["text"])
            ),
            table=_static_table(
                text["testing"]["table"],
                fill(text["testing"]["table_caption"]),
                "tab:testing",
            ),
            subsections=_stress_sections(inputs, text, fill),
            label="sec:testing",
        ),
        Section(
            title=fill(text["dialogue"]["title"]),
            text=fill(text["dialogue"]["text"]),
            label="sec:dialogue",
        ),
        Section(
            title=fill(text["reading"]["title"]),
            text=fill(text["reading"]["text"]),
            table=_static_table(
                text["reading"]["table"],
                fill(text["reading"]["table_caption"]),
                "tab:reading",
            ),
            label="sec:reading",
        ),
        Section(
            title=fill(text["conclusions"]["title"]),
            text=fill(text["conclusions"]["text"]),
        ),
    ]
    if inputs.peers is not None:
        at = next(
            i
            for i, part in enumerate(sections)
            if part.title == fill(text["history"]["title"])
        )
        sections.insert(
            at,
            Section(
                title=fill(text["peers"]["title"]),
                text=fill(text["peers"]["text"]),
                table=replace(
                    _peer_table(inputs, inputs.peers),
                    caption=fill(text["peers"]["table_caption"]),
                    label="tab:peers",
                ),
                figures=[
                    ReportFigure(
                        inputs.figures["peers"],
                        fill(text["peers"]["figure"]),
                        label="fig:peers",
                    )
                ],
            ),
        )
    appendix = [
        Section(
            title=fill(text["appendix"]["title"]),
            text=fill(text["appendix"]["text"]),
            table=replace(
                _lots_table(inputs, text["sectors"]),
                caption=fill(text["appendix"]["table_caption"]),
                label="tab:purchases",
            ),
            label="app:purchases",
        ),
        *_ranking_sections(inputs, text, fill),
        Section(
            title=fill(text["contents"]["appendix_title"]),
            text="",
            table=replace(
                _contents_table(inputs),
                caption=fill(text["contents"]["table_caption"]),
                label="tab:contents",
            ),
            label="app:contents",
        ),
        Section(
            title=fill(text["weighting"]["title"]),
            text="\n\n".join(
                [
                    fill(text["weighting"]["text"]),
                    fill(
                        _verdict(
                            inputs.weighting,
                            text["weighting"]["verdicts"],
                            band=inputs.verdict_band,
                        )
                    ),
                ]
            ),
            table=replace(
                _weighting_table(inputs),
                caption=fill(text["weighting"]["table_caption"]),
                label="tab:weighting",
            ),
            figures=[
                ReportFigure(
                    inputs.figures["weighting"],
                    fill(text["weighting"]["figure"]),
                    width=0.6,
                    label="fig:weighting",
                )
            ],
            label="app:weighting",
        ),
        Section(
            title=fill(text["lookahead"]["title"]),
            text=fill(text["lookahead"]["text"]),
            table=replace(
                _lookahead_table(inputs),
                caption=fill(text["lookahead"]["table_caption"]),
                label="tab:lookahead",
            ),
            label="app:lookahead",
            subsections=[
                Section(
                    title=fill(text["lookahead"]["survivors_title"]),
                    text=fill(text["lookahead"]["survivors_text"]),
                    table=replace(
                        _survivorship_table(inputs),
                        caption=fill(text["lookahead"]["survivors_caption"]),
                        label="tab:survivors",
                    ),
                )
            ],
        ),
        Section(
            title=fill(text["rules"]["list_title"]),
            text=fill(text["rules"]["list_text"]),
            table=replace(
                _rules_table(inputs, text["rule_names"], text["rule_texts"]),
                caption=fill(text["rules"]["list_caption"]),
                label="tab:rules",
            ),
            label="app:rules",
        ),
    ]
    document = Document(
        title=fill(text["title"]),
        subtitle=subtitle,
        abstract=fill(text["abstract"]),
        sections=sections,
        appendix=appendix,
        contents=False,
    )
    return write_latex(folder / "report.tex", document)


def _stress_sections(
    inputs: ReportInputs, text: Mapping[str, Any], fill: Callable[[object], str]
) -> list[Section]:
    """Return the winners-removed subsection, or none when the run was not made."""
    if inputs.stress is None or inputs.stress.empty:
        return []
    return [
        Section(
            title=fill(text["testing"]["winners_title"]),
            text=fill(text["testing"]["winners_text"]),
            table=replace(
                _stress_table(inputs.stress),
                caption=fill(text["testing"]["winners_caption"]),
                label="tab:winners",
            ),
        )
    ]


def _ranking_sections(
    inputs: ReportInputs, text: Mapping[str, Any], fill: Callable[[object], str]
) -> list[Section]:
    """Return the appendix that ranks every scored company, or none without a ranking."""
    if inputs.ranking is None or inputs.ranking.empty:
        return []
    return [
        Section(
            title=fill(text["ranking"]["title"]),
            text=fill(text["ranking"]["text"]),
            table=replace(
                _ranking_table(inputs, inputs.ranking),
                caption=fill(text["ranking"]["caption"]),
                label="tab:ranking",
            ),
            label="app:ranking",
        )
    ]


def _ranking_table(inputs: ReportInputs, ranking: pd.DataFrame) -> Table:
    """Return every scored company by 0-to-1 score, with its colour and a mark on the picks."""
    picks = {str(s) for s in inputs.next_picks["symbol"]}
    rows = [
        [
            f"{int(r['rank'])}",
            _full(inputs, str(r["symbol"])),
            str(r["gics_sector"]),
            f"{float(r['score_share']):.2f}",
            f"{float(r['score']):.1f}",
            _tier(float(r["score_share"]), inputs.tier_cutoffs),
            "Pick" if str(r["symbol"]) in picks else "",
        ]
        for r in ranking.to_dict("records")
    ]
    return Table(
        header=[
            "Rank",
            "Company",
            "Sector",
            "Score 0 to 1",
            "Score",
            "Colour",
            "Next pick",
        ],
        rows=rows,
        columns="r p{4.4cm} p{2.8cm} r r l l",
        fills=_TIER_FILLS,
    )


def _stress_facts(inputs: ReportInputs) -> dict[str, str]:
    """Return the removed companies, largest winner first, for the text."""
    stress = inputs.stress
    if stress is None or stress.empty:
        return {}
    most = int(stress["removed_count"].max())
    symbols = str(stress.loc[stress["removed_count"] == most, "symbols"].tolist()[0])
    if not symbols:
        return {}
    return {"removed": _listing([_full(inputs, s) for s in symbols.split(", ")])}


def _stress_table(stress: pd.DataFrame) -> Table:
    """Return the excess a year per start year and number of winners removed."""
    wide = stress.pivot_table(
        index="scenario", columns="removed_count", values="excess"
    )
    header = ["Start", "As it is"] + [f"Without {int(c)}" for c in wide.columns[1:]]
    rows = [
        [str(start)] + [f"{float(v) * 100:+.1f}" for v in row]
        for start, row in wide.iterrows()
    ]
    return Table(
        header=header,
        rows=rows,
        columns="l" + " r" * (len(header) - 1),
    )


def _named(rule_id: str, names: Mapping[str, str]) -> str:
    """Return ``name (ID)``, or the ID alone when it has no name."""
    return f"{names[rule_id]} ({rule_id})" if rule_id in names else rule_id


def _listing(items: Sequence[str]) -> str:
    """Return ``a, b and c``."""
    if len(items) <= 1:
        return "".join(items) or "none"
    return ", ".join(items[:-1]) + " and " + items[-1]


def _picks_table(inputs: ReportInputs) -> Table:
    """Return the table of each year's picks and what the purchase is worth today."""
    labels = {inputs.compare[0]: inputs.index_label, "BRK-B": "Berkshire"}
    rows = [
        [
            f"{pd.Timestamp(row['decision_date']):%Y-%m}",
            str(row["picks"]),
            f"{float(row['value_usd']):,.0f}",
            *[f"{float(row[f'{s}_usd']):,.0f}" for s in inputs.compare],
        ]
        for row in inputs.held.yearly.to_dict("records")
    ]
    return Table(
        header=[
            "Bought",
            "Picks and weights",
            "Wallet",
            *[labels.get(s, s) for s in inputs.compare],
        ],
        rows=rows,
        columns="l p{9.2cm} " + "r " * (1 + len(inputs.compare)),
    )


def _verdict(check: pd.DataFrame, verdicts: Mapping[str, str], *, band: float) -> str:
    """Return the text's verdict on the weighting from the weight-gap correlation.

    Above ``band`` the weighting favours the right rules, below ``-band`` the wrong ones,
    in between the two are unrelated.
    """
    value = weighting_quality(check)["weight_vs_gap"]
    if value > band:
        return str(verdicts["favours"])
    if value < -band:
        return str(verdicts["against"])
    return str(verdicts["unrelated"])


def _rules_table(
    inputs: ReportInputs, names: Mapping[str, str], texts: Mapping[str, Any]
) -> Table:
    """Return each rule: name, what it measures, the better direction and the pass."""
    rows: list[list[str]] = []
    for rule_id, settings in inputs.rules.items():
        own = texts.get(rule_id, {})
        rows.append(
            [
                rule_id,
                names.get(rule_id, rule_id),
                str(own.get("measures", "")).format(**settings),
                "higher" if RULES[rule_id].higher_is_better else "lower",
                str(own.get("passes", "")).format(**settings),
            ]
        )
    return Table(
        header=["Rule", "Name", "What it measures", "Better", "Passes when"],
        rows=rows,
        columns="l p{2.2cm} p{5.2cm} l p{2.8cm}",
    )


def _weighting_table(inputs: ReportInputs) -> Table:
    """Return each rule's weights and how well it told winners from losers."""
    check = inputs.weighting.sort_values("weight", ascending=False)
    rows = [
        [
            str(r["rule"]),
            f"{float(r['weight']):.2f}",
            f"{float(r['weight_beat']):.2f}",
            f"{float(r['weight_not']):.2f}",
            f"{float(r['points_beat']):.2f}",
            f"{float(r['points_not']):.2f}",
            f"{float(r['gap']):+.2f}",
            f"{float(r['ic']):+.2f}",
        ]
        for r in check.to_dict("records")
    ]
    return Table(
        header=[
            "Rule",
            "w_r",
            "w_r beat",
            "w_r not",
            "Pts beat",
            "Pts not",
            "Gap",
            "Corr.",
        ],
        rows=rows,
        columns="l r r r r r r r",
    )


def _summary_table(inputs: ReportInputs) -> Table:
    """Return money put in, value, multiple and return a year, grouped by start year."""
    summary = pd.concat(
        [inputs.held.summary, inputs.managed.summary], ignore_index=True
    )
    order = [WALLET, MANAGED, *inputs.compare]
    rows: list[list[str]] = []
    breaks: list[int] = []
    for start, part in summary.groupby("scenario", sort=True):
        by = part.set_index("holder")
        for index, holder in enumerate(h for h in order if h in by.index):
            row = by.loc[[holder]].iloc[0]
            rows.append(
                [
                    str(start) if index == 0 else "",
                    {**LABELS, inputs.compare[0]: inputs.index_label}.get(
                        holder, holder
                    ),
                    f"{float(row['invested_usd']):,.0f}",
                    f"{float(row['value_usd']):,.0f}",
                    f"{float(row['multiple']):.2f}",
                    f"{float(row['annual_return']):.1%}",
                ]
            )
        breaks.append(len(rows) - 1)
    return Table(
        header=["Start", "Holder", "Put in", "Value", "Multiple", "A year"],
        rows=rows,
        columns="l l r r r r",
        breaks=tuple(breaks),
    )


def _contents_table(inputs: ReportInputs) -> Table:
    """Return the reference investor's wallet: each holding's value after each January.

    One column per January decision (holdings after its sales and purchases) and one
    for the valuation date; the last rows give the money put in and the sale proceeds
    to date, July decisions included, and the total of each column.
    """
    first = inputs.reference
    contents = inputs.managed.contents
    own = contents[contents["scenario"] == first]
    trades = inputs.managed.trades
    trades = trades[trades["scenario"] == first]
    decisions = sorted(pd.Timestamp(d) for d in trades["decision_date"].unique())
    januaries = [d for d in decisions if d.month == 1]
    columns = [*januaries, pd.Timestamp(inputs.end)]
    wide = own.pivot_table(
        index="symbol", columns="date", values="value_usd", aggfunc="sum"
    ).reindex(columns=columns)
    bought = trades[trades["action"] == "buy"].groupby("symbol")["decision_date"].min()
    order = [s for s in bought.sort_values().index if s in wide.index]
    order += [s for s in wide.index if s not in order]
    # Leave out rows with nothing in them (cash that was never left unspent).
    order = [s for s in order if (wide.loc[[s]].to_numpy() >= HALF_CENT).any()]
    values = wide.reindex(order).to_numpy(dtype=float)
    rows = [
        [str(symbol)]
        + ["" if not value >= HALF_CENT else f"{value:,.0f}" for value in line]
        for symbol, line in zip(order, values.tolist(), strict=True)
    ]
    sales = trades[trades["action"] == "sell"]
    rows.append(
        ["Put in"]
        + [
            f"{inputs.amount * sum(1 for d in decisions if d <= c):,.0f}"
            for c in columns
        ]
    )
    rows.append(
        ["Sold"]
        + [
            f"{float(sales.loc[sales['decision_date'] <= c, 'usd'].sum()):,.0f}"
            for c in columns
        ]
    )
    rows.append(["Total"] + [f"{float(wide[c].sum()):,.0f}" for c in columns])
    return Table(
        header=["Holding", *[f"{d:%Y}" for d in januaries], "Now"],
        rows=rows,
        columns="l " + "r " * len(columns),
        breaks=(len(order) - 1,),
    )


def _sales_table(inputs: ReportInputs) -> Table:
    """Return the sales of the reference investor's wallet, one row per sale."""
    trades = inputs.managed.trades
    first = inputs.reference
    sales = trades[(trades["scenario"] == first) & (trades["action"] == "sell")]
    rows = [
        [
            f"{pd.Timestamp(part['decision_date'].iloc[0]):%Y-%m}",
            ", ".join(
                f"{r.symbol} {r.fraction:.0%} (score {r.score_share:.2f})"
                for r in part.itertuples()
            ),
            f"{float(part['usd'].sum()):,.2f}",
        ]
        for _, part in sales.groupby("decision_date", sort=True)
    ]
    return Table(
        header=["Year", "Sold: share of the holding (score)", "Proceeds, USD"],
        rows=rows,
        columns="l p{11cm} r",
    )


def _next_table(inputs: ReportInputs, sectors: Mapping[str, str]) -> Table:
    """Return the next picks, named in full, with their score and USD of each 100 USD."""
    rows = [
        [
            _full(inputs, str(r["symbol"])),
            sectors.get(str(r["gics_sector"]), str(r["gics_sector"])),
            f"{float(r['score']):.1f}",
            f"{float(r['score_share']):.2f}",
            f"{float(r['weight']):.1%}",
            f"{inputs.amount * float(r['weight']):.2f}",
        ]
        for r in inputs.next_picks.to_dict("records")
    ]
    return Table(
        header=["Company", "Sector", "Score", "Score 0 to 1", "Weight", "USD"],
        rows=rows,
        columns="l l r r r r",
    )


def _static_table(spec: Mapping[str, Any], caption: str, label: str) -> Table:
    """Return a table written out in the report text: ``header``, ``rows``, ``columns``."""
    return Table(
        header=[str(h) for h in spec["header"]],
        rows=[[str(cell) for cell in row] for row in spec["rows"]],
        columns=str(spec["columns"]),
        caption=caption,
        label=label,
    )


_TIER_FILLS = {
    "Green": "C6EFCE",
    "Amber": "FFEB9C",
    "Red": "F4B6B6",
    "Black": "BFBFBF",  # grey: a black cell would hide its text
}


def _tier(share: float, cutoffs: Sequence[float]) -> str:
    """Return the colour of a 0-to-1 score.

    Green above ``cutoffs[0]``; Amber above ``cutoffs[1]`` up to and including
    ``cutoffs[0]``; Red above ``cutoffs[2]`` up to and including ``cutoffs[1]``;
    Black at or below ``cutoffs[2]``, down to 0.
    """
    green, amber, red = cutoffs
    if share > green:
        return "Green"
    if share > amber:
        return "Amber"
    return "Red" if share > red else "Black"


def _worst_table(inputs: ReportInputs) -> Table:
    """Return the lowest scores of the index with the tier each one falls in."""
    rows = [
        [
            _full(inputs, str(r["symbol"])),
            str(r["gics_sector"]),
            f"{float(r['score']):.1f}",
            f"{float(r['score_share']):.2f}",
            _tier(float(r["score_share"]), inputs.tier_cutoffs),
        ]
        for r in inputs.worst.to_dict("records")
    ]
    return Table(
        header=["Company", "Sector", "Score", "Score 0 to 1", "Colour"],
        rows=rows or [["none", "", "", "", ""]],
        columns="p{4.4cm} p{3cm} r r p{3cm}",
        fills=_TIER_FILLS,
    )


def _lookahead_table(inputs: ReportInputs) -> Table:
    """Return the truncation check: companies whose score changes when inputs are cut."""
    check = inputs.lookahead
    differ = [c for c in check.columns if c.startswith("differ_")]
    rows = [
        [
            f"{pd.Timestamp(r['date']):%Y-%m-%d}",
            str(int(r["companies"])),
            *[str(int(r[c])) for c in differ],
            "yes" if bool(r["same_top"]) else "no",
        ]
        for r in check.to_dict("records")
    ]
    return Table(
        header=[
            "Date",
            "Companies",
            *[SCORE_LABELS.get(c.removeprefix("differ_"), c) for c in differ],
            "Same picks",
        ],
        rows=rows,
        columns="l r " + "r " * len(differ) + "l",
    )


def _survivorship_table(inputs: ReportInputs) -> Table:
    """Return, per start year, the companies that left the index since then."""
    rows = [
        [
            str(int(r["start"])),
            str(int(r["removed"])),
            str(int(r["market_cap"])),
            str(int(r["removed"]) - int(r["market_cap"])),
        ]
        for r in inputs.survivorship.to_dict("records")
    ]
    return Table(
        header=["Start", "Left the index", "On market value", "Acquired or other"],
        rows=rows,
        columns="l r r r",
    )


def _lookahead_facts(inputs: ReportInputs) -> dict[str, str]:
    """Return the facts of the truncation check."""
    check = inputs.lookahead
    differ = [c for c in check.columns if c.startswith("differ_")]
    clean = check[(check[differ] == 0).all(axis=1)]
    return {
        "lookahead_dates": _listing(
            [f"{pd.Timestamp(d):%d %B %Y}" for d in check["date"]]
        ),
        "lookahead_clean": _listing(
            [f"{pd.Timestamp(d):%d %B %Y}" for d in clean["date"]]
        ),
        "lookahead_picks": (
            "the same" if bool(check["same_top"].all()) else "not the same"
        ),
    }


def _peer_table(inputs: ReportInputs, group: Peers) -> Table:
    """Return each peer's score, rank today and median rank on the decisions."""
    rows = [
        [
            _full(inputs, str(r["symbol"])),
            "" if pd.isna(r["score"]) else f"{float(r['score']):.1f}",
            "" if pd.isna(r["share"]) else f"{float(r['share']):.2f}",
            (
                ""
                if pd.isna(r["rank"])
                else f"{float(r['rank']):.0f} of {float(r['companies']):.0f}"
            ),
            "" if pd.isna(r["median_rank"]) else f"{float(r['median_rank']):.0f}",
        ]
        for r in group.ranks.sort_values("rank").to_dict("records")
    ]
    return Table(
        header=["Company", "Score", "Score 0 to 1", "Rank today", "Median rank"],
        rows=rows,
        columns="l r r r r",
    )


def _lots_table(inputs: ReportInputs, sectors: Mapping[str, str]) -> Table:
    """Return every purchase of the reference investor's wallet with sells.

    Each purchase shows what later sales took from it and what it keeps today;
    ``sectors`` shortens the sector names.
    """
    first = inputs.reference
    purchases = inputs.managed.purchases
    own = purchases[purchases["scenario"] == first].copy()
    yearly = own.groupby("decision_date")["invested_usd"].transform("sum")
    own["weight"] = own["invested_usd"] / yearly
    sector_of = dict(
        zip(inputs.held.lots["symbol"], inputs.held.lots["gics_sector"], strict=True)
    )
    rows = [
        [
            f"{pd.Timestamp(row['decision_date']):%Y-%m}",
            str(row["symbol"]),
            sectors.get(str(sector_of.get(row["symbol"], "")), "")
            or str(sector_of.get(row["symbol"], "")),
            f"{float(row['weight']):.0%}",
            f"{float(row['invested_usd']):,.0f}",
            f"{float(row['buy_price']):,.2f}",
            f"{float(row['last_price']):,.2f}",
            (
                ""
                if float(row["sold_usd"]) < HALF_CENT
                else f"{float(row['sold_usd']):,.0f}"
            ),
            f"{float(row['kept_usd']):,.0f}",
            f"{float(row['total_return']):+.0%}",
        ]
        for row in own.sort_values(
            ["decision_date", "weight"], ascending=[True, False]
        ).to_dict("records")
    ]
    return Table(
        header=[
            "Year",
            "Company",
            "Sector",
            "Weight",
            "In",
            "Bought at",
            "Now",
            "Sold",
            "Kept",
            "Return",
        ],
        rows=rows,
        columns="l l l r r r r r r r",
    )
