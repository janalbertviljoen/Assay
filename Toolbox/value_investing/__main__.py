r"""
value_investing/__main__.py
---------------------------
The terminal command that scores buyability and writes its diagnostic plots.

Run from the repository root, after ``python -m Toolbox.market_data update``::

    .venv/bin/python -m Toolbox.value_investing buyability --as-of 2026-10-31 --index sp400
    .venv/bin/python -m Toolbox.value_investing evaluate --as-of 2026-10-31 --index sp400
    .venv/bin/python -m Toolbox.value_investing report --as-of 2026-10-31 --index sp400

Every command works on one index of ``config/indices.toml`` (``--index``, default
``sp500``): its members are the universe and its benchmark the comparison. It reads the
stored tables of the as-of date, each checked against its schema in
``value_investing.schema.INPUT_TABLES`` as it is read (``market_data.validation.check_table``),
runs ``value_investing.pipeline`` with ``config/rules.toml``, writes the buyability table to
``data/interim/value_investing/<as_of>/<index>/buyability_<view>.parquet`` per universe
view, and the plots and the sample to ``results/value_investing/<index>/<as_of>/buyability/``;
``buyability`` prints each view's pipeline report (the soft-expectation notices).
The stored buyability tables are this tool's own output and are not checked when
``evaluate`` and ``report`` read them.
``evaluate`` reads that table and writes the paper test of the score
(``value_investing.evaluation``) and the ledger of one wallet (``value_investing.ledger``:
``ledger.md``, ``ledger.csv``, ``ledger_balance.csv``) to
``results/value_investing/<index>/<as_of>/evaluation/``. ``report`` writes the
buy-and-hold report (``value_investing.holding``, ``value_investing.report``) to
``results/value_investing/<index>/<as_of>/report/`` and compiles it when a LaTeX engine
is found.

Owns
----
The command-line interface, the file layout of the outputs and the summary printed.

Must not
--------
Compute flags, scores, diagnostics or the evaluation (``value_investing.pipeline``,
``value_investing.diagnostics``, ``value_investing.evaluation``).

Public API
----------
main(argv)
    Run ``buyability``, ``evaluate`` or ``report``; returns the exit code.
evaluation_settings(rules)
    The ``[evaluation]`` settings of ``config/rules.toml``, with ``[score]
    min_companies``.

Dependency rule
---------------
The standard library, pandas, ``skatkis.io``, ``market_data`` and ``value_investing``.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from Toolbox.market_data.sources.prices import yahoo_symbol
from Toolbox.market_data.validation import check_table
from Toolbox.skatkis.io.config import load_config
from Toolbox.skatkis.io.figures import save_figure
from Toolbox.skatkis.io.tables import read_table, write_table
from Toolbox.skatkis.report import compile_pdf
from Toolbox.value_investing import (
    diagnostics,
    evaluation,
    holding,
    ledger,
    lookahead,
    peers,
    plots,
    report,
)
from Toolbox.value_investing.inputs import index_universe, price_on
from Toolbox.value_investing.pipeline import Buyability, Tables, buyability
from Toolbox.value_investing.schema import INPUT_TABLES


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``buyability``, ``evaluate`` or ``report`` command."""
    args = _parser().parse_args(argv)
    if args.command == "evaluate":
        return _evaluate(args)
    if args.command == "report":
        return _report(args)
    return _buyability(args)


LATEX_ENGINES = ("tectonic", "latexmk", "pdflatex")


@dataclass(frozen=True)
class _Index:
    """The index a command works on, and where its tables and results live."""

    key: str
    label: str
    benchmark: str
    benchmark_name: str
    membership: str
    interim: Path
    tables: Path
    members: Path
    results: Path


def _index(args: argparse.Namespace) -> _Index:
    """Return the ``--index`` entry of ``config/indices.toml`` and its folders."""
    entry = load_config(args.indices)[args.index]
    as_of = args.as_of.isoformat()
    interim = args.data_dir / "interim"
    return _Index(
        key=args.index,
        label=str(entry["label"]),
        benchmark=str(entry["benchmark"]),
        benchmark_name=str(entry["benchmark_name"]),
        membership=str(entry["membership"]),
        interim=interim,
        tables=interim / "value_investing" / as_of / args.index,
        members=interim / "constituents" / as_of / args.index,
        results=args.results_dir / "value_investing" / args.index / as_of,
    )


def _buyability(args: argparse.Namespace) -> int:
    """Score buyability for the as-of date and write the table, sample and plots."""
    rules = load_config(args.rules)
    market = load_config(args.market_config)
    index = _index(args)
    tables = _load_tables(index, args.as_of.isoformat(), rules, market)
    prices, universe = tables.prices, tables.universe
    benchmark = index.benchmark
    folder = index.results / "buyability"
    folder.mkdir(parents=True, exist_ok=True)
    views = [str(v) for v in rules["universe"]["views"]]
    results: dict[str, Buyability] = {}
    for view in views:
        result = buyability(
            tables, rules, end=pd.Timestamp(args.as_of), view=view, benchmark=benchmark
        )
        dates = sorted(result.table["date"].unique())
        excess = diagnostics.forward_excess(
            prices, universe["symbol"], dates, benchmark=benchmark
        )
        table = result.table.merge(
            excess.reset_index(), on=["symbol", "date"], how="left"
        )
        write_table(table, index.tables / f"buyability_{view}.parquet")
        result.weights.to_csv(folder / f"rule_weights_{view}.csv", float_format="%.4f")
        results[view] = replace(result, table=table)
    # The diagnostics describe the first view.
    first = results[views[0]]
    table = first.table
    dates = sorted(table["date"].unique())

    settings = rules["diagnostics"]
    start = pd.Timestamp(settings["mean_from"])
    chosen = diagnostics.sample(table, mean_from=start, n=int(settings["companies"]))
    levels = price_on(
        prices,
        pd.concat([chosen["symbol"], pd.Series([benchmark])]),
        dates,
        column="adj_close",
    ).reset_index()
    paths = diagnostics.sample_paths(
        table, chosen, levels, benchmark=benchmark, start=start
    )
    recent = table[table["date"] >= start]
    returns = diagnostics.score_returns(recent, bin_width=0.1)
    ic = diagnostics.information_coefficient(
        table, min_companies=int(rules["score"]["min_companies"])
    )

    chosen.to_csv(folder / "sample.csv", index=False, float_format="%.2f")
    returns.to_csv(folder / "score_returns.csv", index=False, float_format="%.4f")
    pass_columns = [c for c in table.columns if c.endswith("_pass")]
    figures = {
        "score_spread": plots.score_spread(table),
        "rule_pass_rates": plots.rule_rates(table, pass_columns, evaluable=False),
        "rule_coverage": plots.rule_rates(table, pass_columns, evaluable=True),
        "sample_best": plots.sample_paths(paths, "best"),
        "sample_worst": plots.sample_paths(paths, "worst"),
        "sample_signal_best": plots.sample_signal(paths, "best"),
        "sample_signal_worst": plots.sample_signal(paths, "worst"),
        "score_against_return": plots.score_against_return(returns),
        "information_coefficient": plots.information_coefficient(ic),
        "rule_weights": plots.rule_weights(first.weights),
    }
    for name, figure in figures.items():
        save_figure(figure, folder / f"{name}.png")

    print(f"Views {', '.join(views)}; diagnostics on {views[0]}")
    for view, result in results.items():
        print(f"{view}: {result.report.summary()}")
    print(
        f"{table['symbol'].nunique()} companies, {len(dates)} rebalance dates "
        f"({dates[0]:%Y-%m-%d} to {dates[-1]:%Y-%m-%d}), {len(pass_columns)} rules"
    )
    print(f"Sample (mean score from {start:%Y-%m-%d}):")
    print(chosen.to_string(index=False, float_format="%.2f"))
    print(
        f"Mean rank correlation from {start:%Y-%m-%d}: "
        f"{ic[ic['date'] >= start]['ic'].mean():.3f}"
    )
    print(f"{len(figures)} plots in {folder}")
    return 0


def _evaluate(args: argparse.Namespace) -> int:
    """Run the paper test of the stored buyability table and write tables and plots."""
    rules = load_config(args.rules)
    index = _index(args)
    views = [str(v) for v in rules["universe"]["views"]]
    tables = {
        view: read_table(index.tables / f"buyability_{view}.parquet") for view in views
    }
    # The detailed evaluation describes the first view; the comparison covers all.
    table = tables[views[0]]
    prices = _read(index.interim / "yahoo" / args.as_of.isoformat(), "prices")
    benchmark = index.benchmark
    settings = evaluation_settings(rules)
    trading_days = prices[prices["symbol"] == benchmark]["date"]
    end = pd.Timestamp(trading_days.max())
    decisions = evaluation.decision_dates(
        list(trading_days), first_year=settings.first_year
    )
    signal_table = evaluation.signals(table, decisions, settings)
    held = evaluation.holdings(
        signal_table, prices, settings, benchmark=benchmark, end=end
    )
    wallet_table = evaluation.wallets(held, settings)
    score = evaluation.model_score(wallet_table, settings)
    rebalances = sorted(
        d for d in table["date"].unique() if d.year >= settings.first_year
    )
    curve = evaluation.correlation_curve(
        table, prices, rebalances, settings, benchmark=benchmark
    )
    held["period"] = [settings.period(pd.Timestamp(d)) for d in held["decision_date"]]
    summary = (
        held.groupby(["side", "period", "horizon_months"])
        .agg(
            positions=("excess", "size"),
            hit_rate=("beat", "mean"),
            mean_excess=("excess", "mean"),
            median_excess=("excess", "median"),
        )
        .reset_index()
    )

    horizon = settings.score_horizon_months
    comparison, paths, positions = _compare(
        tables, _Run(table, prices, decisions, settings, benchmark), rules
    )
    book = _ledger(_Run(table, prices, decisions, settings, benchmark), rules)

    folder = index.results / "evaluation"
    folder.mkdir(parents=True, exist_ok=True)
    score.to_csv(folder / "model_score.csv", index=False, float_format="%.4f")
    comparison.to_csv(folder / "model_comparison.csv", index=False, float_format="%.4f")
    positions.to_csv(folder / "ranked_positions.csv", index=False, float_format="%.4f")
    summary.to_csv(folder / "horizons.csv", index=False, float_format="%.4f")
    wallet_table.to_csv(folder / "wallets.csv", index=False, float_format="%.4f")
    curve.to_csv(folder / "correlation_curve.csv", index=False, float_format="%.4f")
    figures = {
        "model_growth": plots.model_paths(paths, benchmark=benchmark),
        "wallet_growth": plots.wallet_paths(
            wallet_table, horizon=horizon, benchmark=benchmark
        ),
        "yearly_excess": plots.yearly_excess(wallet_table, horizon=horizon),
        "hit_rate_by_horizon": plots.horizon_profile(
            summary,
            y="hit_rate",
            ylabel=f"Share of positions beating {benchmark}",
            title="Hit rate per holding horizon",
            threshold=0.5,
        ),
        "excess_by_horizon": plots.horizon_profile(
            summary,
            y="mean_excess",
            ylabel="Mean excess return per position",
            title=f"Mean excess over {benchmark} per holding horizon",
            threshold=0.0,
        ),
        "correlation_curve": plots.correlation_curve(curve),
    }
    for name, figure in figures.items():
        save_figure(figure, folder / f"{name}.png")
    _write_ledger(book, rules, folder, views[0], benchmark)

    print(
        f"{len(decisions)} decision dates ({decisions[0]:%Y-%m-%d} to "
        f"{decisions[-1]:%Y-%m-%d}), buy >= {settings.buy_threshold}, "
        f"sell <= {settings.sell_threshold}; prices to {end:%Y-%m-%d}"
    )
    print(f"Model score (buy wallet, {horizon} months, annualised excess):")
    print(score.to_string(index=False, float_format="%.4f"))
    print("Per horizon:")
    print(summary.to_string(index=False, float_format="%.4f"))
    peak = curve.groupby(["period", "horizon_months"])["ic"].mean()
    for period, part in peak.groupby(level="period"):
        best = part.droplevel("period")
        print(
            f"Rank correlation, {period}: peak {best.max():.3f} at "
            f"{best.idxmax()} months"
        )
    print(f"Models ({horizon} months, annualised excess over {benchmark}):")
    print(
        comparison.pivot_table(
            index="model", columns=["universe", "period"], values="annualised_excess"
        ).to_string(float_format="%.4f")
    )
    print(f"Ledger ({views[0]} universe), balance per decision:")
    print(book.balance.to_string(index=False, float_format="%.2f"))
    print(f"{len(figures)} plots in {folder}")
    return 0


@dataclass(frozen=True)
class _Run:
    """What every model of one evaluation run shares."""

    table: pd.DataFrame
    prices: pd.DataFrame
    decisions: list[pd.Timestamp]
    settings: evaluation.Evaluation
    benchmark: str


def _ledger(run: _Run, rules: dict[str, Any]) -> ledger.Ledger:
    """Return the ledger of the wallet named in ``[ledger]``, on ``run.table``."""
    raw = rules["wallet"]
    model = evaluation.Wallet(
        score_column=str(rules["ledger"]["score_column"]),
        weighting="score",
        names=int(raw["names"]),
        book_usd=float(raw["book_usd"]),
        horizon_months=int(raw["horizon_months"]),
        rank_weights=tuple(float(w) for w in raw["rank_weights"]),
    )
    positions = evaluation.ranked_positions(run.table, run.decisions, model)
    sectors = run.table[["symbol", "gics_sector"]].drop_duplicates("symbol")
    positions = positions.merge(sectors, on="symbol", how="left")
    return ledger.ledger(
        positions,
        run.prices,
        benchmark=run.benchmark,
        others=list(rules["ledger"]["compare"]),
        months=model.horizon_months,
        start_usd=float(rules["ledger"]["start_usd"]),
    )


def _write_ledger(
    book: ledger.Ledger, rules: dict[str, Any], folder: Path, view: str, benchmark: str
) -> None:
    """Write the ledger's tables, its Markdown page and its balance plot."""
    book.positions.to_csv(folder / "ledger.csv", index=False, float_format="%.4f")
    book.balance.to_csv(folder / "ledger_balance.csv", index=False, float_format="%.4f")
    (folder / "ledger.md").write_text(_ledger_markdown(book, rules, view))
    title = (
        f"Balance of {rules['ledger']['start_usd']:g} USD: "
        f"{rules['ledger']['score_column']}, top {rules['wallet']['names']}, "
        f"{view} universe"
    )
    others = {
        str(s): ledger.comparison_name(str(s)) for s in rules["ledger"]["compare"]
    }
    save_figure(
        plots.balance(book.balance, title=title, others=others, benchmark=benchmark),
        folder / "ledger_balance.png",
    )


def _ledger_markdown(book: ledger.Ledger, rules: dict[str, Any], view: str) -> str:
    """Return the ledger as a Markdown page: the balance, then each year's positions."""
    names = rules["wallet"]["names"]
    column = rules["ledger"]["score_column"]
    others = [str(s) for s in rules["ledger"]["compare"]]
    lines = [
        "# Value wallet ledger",
        "",
        f"Top {names} companies by `{column}` ({view} universe), bought on the first "
        "trading day of each year with the whole balance, weighted by score, and sold "
        "on the next year's first trading day. Total return includes dividends; no "
        "costs or taxes. Prices are split-adjusted to the data's as-of date, so they "
        "differ from the quotes of the day for companies that split later. The same "
        "money is followed in the S&P 500 (total return) and in "
        + ", ".join(others)
        + ". Generated by `python -m Toolbox.value_investing evaluate`.",
        "",
        "## Balance",
        "",
        "| Bought | Sold | Wallet start | Wallet end | Return | S&P 500 end | "
        "S&P 500 return | "
        + "".join(f"{s} end | {s} return | " for s in others)
        + "Ahead of S&P 500 |",
        "|---|---|" + "---:|" * (6 + 2 * len(others)),
    ]
    for row in book.balance.to_dict("records"):
        cells = [
            f"{pd.Timestamp(row['decision_date']):%Y-%m-%d}",
            f"{pd.Timestamp(row['sell_date']):%Y-%m-%d}",
            f"{row['start_usd']:,.2f}",
            f"{row['end_usd']:,.2f}",
            f"{row['wallet_return']:+.1%}",
            f"{row['benchmark_end_usd']:,.2f}",
            f"{row['benchmark_return']:+.1%}",
        ]
        for symbol in others:
            name = ledger.comparison_name(symbol)
            cells += [f"{row[f'{name}_end_usd']:,.2f}", f"{row[f'{name}_return']:+.1%}"]
        cells.append(f"{row['ahead_usd']:+,.2f}")
        lines.append("| " + " | ".join(cells) + " |")
    for _, part in book.positions.groupby("decision_date", sort=True):
        bought = pd.Timestamp(part["decision_date"].iloc[0])
        lines += [
            "",
            f"## Bought {bought:%Y-%m-%d}",
            "",
            "| Company | Sector | Score | Weight | Invested | Buy price | Sell price | "
            "Price change | Total return | Value | Gain |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for row in part.itertuples(index=False):
            lines.append(
                f"| {row.symbol} | {row.gics_sector} | {row.score:.1f} "
                f"| {row.weight:.1%} | {row.invested_usd:,.2f} | {row.buy_price:,.2f} "
                f"| {row.sell_price:,.2f} | {row.price_change:+.1%} "
                f"| {row.total_return:+.1%} | {row.value_usd:,.2f} "
                f"| {row.gain_usd:+,.2f} |"
            )
    return "\n".join(lines) + "\n"


def _report(args: argparse.Namespace) -> int:
    """Write the buy-and-hold report's figures and LaTeX, and compile it to PDF."""
    rules = load_config(args.rules)
    as_of = args.as_of.isoformat()
    index = _index(args)
    view = str(rules["universe"]["views"][0])
    table = read_table(index.tables / f"buyability_{view}.parquet")
    prices = _read(index.interim / "yahoo" / as_of, "prices")
    settings = rules["report"]
    compare = [index.benchmark, *[str(s) for s in settings["compare"]]]
    start_years = [int(y) for y in settings["start_years"]]
    trading_days = prices[prices["symbol"] == compare[0]]["date"]
    end = pd.Timestamp(trading_days.max())
    decisions = evaluation.decision_dates(
        list(trading_days),
        first_year=min(start_years),
        months=[int(m) for m in settings["decision_months"]],
    )
    model = evaluation.Wallet(
        score_column=str(rules["ledger"]["score_column"]),
        weighting="score",
        names=int(rules["wallet"]["names"]),
        book_usd=float(settings["amount_usd"]),
        horizon_months=int(rules["wallet"]["horizon_months"]),
        rank_weights=tuple(float(w) for w in rules["wallet"]["rank_weights"]),
    )
    positions = evaluation.ranked_positions(table, decisions, model).merge(
        table[["symbol", "gics_sector"]].drop_duplicates("symbol"), on="symbol"
    )
    held = holding.buy_and_hold(
        positions,
        prices,
        compare=compare,
        amount_usd=float(settings["amount_usd"]),
        start_years=start_years,
        end=end,
    )
    profile = holding.rule_profile(held.lots, table, list(rules["rules"]))
    weighting = holding.rule_weighting(held.lots, table, list(rules["rules"]))
    market = load_config(args.market_config)
    check = lookahead.truncation_check(
        _load_tables(index, as_of, rules, market),
        rules,
        table,
        [pd.Timestamp(d) for d in settings["lookahead_dates"]],
        view=view,
        benchmark=index.benchmark,
        columns=[
            model.score_column,
            str(settings["share_column"]),
            "score_binned",
            "score",
        ],
        top=model.names,
    )
    peer_view = _peer_view(
        _Run(table, prices, decisions, evaluation_settings(rules), compare[0]),
        held,
        model,
        rules,
    )
    shares = table.set_index(["symbol", "date"])[str(settings["share_column"])]
    managed = holding.buy_and_sell(
        positions,
        shares,
        prices,
        threshold=float(settings["sell_threshold"]),
        amount_usd=float(settings["amount_usd"]),
        start_years=start_years,
        end=end,
    )
    now = evaluation.ranked_positions(table, [end], model)
    now = now.merge(
        table[["symbol", "date", "gics_sector", str(settings["share_column"])]],
        left_on=["symbol", "score_date"],
        right_on=["symbol", "date"],
    ).rename(columns={str(settings["share_column"]): "score_share"})
    upcoming = now[now["side"] == "buy"]
    worst = now[now["side"] == "sell"].sort_values(["score", "symbol"])
    changes = _read(index.members, "changes")
    paths = pd.concat([held.paths, managed.paths], ignore_index=True)

    folder = index.results / "report"
    folder.mkdir(parents=True, exist_ok=True)
    figures = {
        "yearly": save_figure(
            plots.yearly_purchases(held.yearly, compare), folder / "yearly.png"
        ),
        "contents": save_figure(
            plots.wallet_contents(
                managed.contents,
                held.paths,
                min(start_years),
                compare,
                limit=int(settings["pick_page"]),
            ),
            folder / "contents.png",
        ),
        "weighting": save_figure(
            plots.weighting_check(weighting), folder / "weighting.png"
        ),
        "rules": save_figure(
            plots.rule_profile(profile, load_config(args.report_text)["rule_names"]),
            folder / "rules.png",
        ),
    }
    figures.update(
        _price_figures(prices, managed.trades, upcoming, worst, settings, folder)
    )
    if peer_view is not None:
        figures["peers"] = save_figure(
            plots.peer_profile(peer_view.profile, peer_view.label),
            folder / "peers.png",
        )
    for start in start_years:
        figures[f"value_{start}"] = save_figure(
            plots.held_value(paths, start, index.benchmark),
            folder / f"value_{start}.png",
        )
    held.lots.to_csv(folder / "purchases.csv", index=False, float_format="%.4f")
    summary = pd.concat([held.summary, managed.summary], ignore_index=True)
    summary.to_csv(folder / "summary.csv", index=False, float_format="%.4f")
    managed.trades.to_csv(folder / "trades.csv", index=False, float_format="%.4f")
    managed.holdings.to_csv(folder / "holdings.csv", index=False, float_format="%.4f")
    weighting.to_csv(folder / "weighting.csv", index=False, float_format="%.4f")
    upcoming.to_csv(folder / "next_picks.csv", index=False, float_format="%.4f")
    worst[["symbol", "gics_sector", "score", "score_share", "score_date"]].to_csv(
        folder / "worst_stocks.csv", index=False, float_format="%.4f"
    )
    report_text = load_config(args.report_text)
    inputs = report.ReportInputs(
        held=held,
        managed=managed,
        next_picks=upcoming,
        worst=worst,
        profile=profile,
        weighting=weighting,
        peers=peer_view,
        lookahead=check,
        survivorship=diagnostics.survivorship(changes, start_years),
        reference=int(settings["reference_start"]),
        names=_company_names(index.members / "constituents.parquet"),
        index_label=index.label,
        benchmark_name=index.benchmark_name,
        membership=index.membership,
        record_start=pd.Timestamp(changes["date"].min()),
        pick_scenario=int(settings["pick_scenario"]),
        pick_years=int(settings["pick_years"]),
        pick_ends=int(settings["pick_ends"]),
        rules={
            rule_id: {**rules["valuation"], **thresholds}
            for rule_id, thresholds in rules["rules"].items()
        },
        figures=figures,
        compare=compare,
        amount=float(settings["amount_usd"]),
        picks=model.names,
        end=end,
        threshold=float(settings["sell_threshold"]),
        tier_cutoffs=[float(c) for c in settings["tier_cutoffs"]],
        verdict_band=float(settings["verdict_band"]),
        static_note=_static_note(rules, report_text, as_of),
        ranking=_ranking(
            table, end, model, str(settings["share_column"]), folder / "ranking.csv"
        ),
        stress=_winner_stress(
            table,
            prices,
            decisions,
            model,
            held,
            counts=[int(n) for n in settings["winners_removed"]],
            compare=compare,
            amount_usd=float(settings["amount_usd"]),
            start_years=start_years,
            end=end,
        ),
    )
    tex = report.build_report(
        inputs,
        report_text,
        folder=folder,
        subtitle=f"{index.label}, data as of {as_of}",
    )
    print(summary.to_string(index=False, float_format="%.3f"))
    print("Next picks:")
    print(upcoming[["symbol", "score", "score_share", "weight"]].to_string(index=False))
    return _compile(tex, args.data_dir)


def _ranking(
    table: pd.DataFrame,
    end: pd.Timestamp,
    model: evaluation.Wallet,
    share_column: str,
    path: Path,
) -> pd.DataFrame:
    """Return every scored company, best 0-to-1 score first, with its sector and score.

    Also writes it to ``path``.
    """
    ranked = evaluation.ranking(
        table, end, by=share_column, columns=["gics_sector", model.score_column]
    ).rename(columns={share_column: "score_share", model.score_column: "score"})
    ranked[
        ["rank", "symbol", "gics_sector", "score", "score_share", "score_date"]
    ].to_csv(path, index=False, float_format="%.4f")
    return ranked


def _winner_stress(  # noqa: PLR0913  one argument per setting of the run
    table: pd.DataFrame,
    prices: pd.DataFrame,
    decisions: Sequence[pd.Timestamp],
    model: evaluation.Wallet,
    held: holding.BuyAndHold,
    *,
    counts: Sequence[int],
    compare: Sequence[str],
    amount_usd: float,
    start_years: Sequence[int],
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Return the wallet's excess with the ``counts`` largest winners taken out.

    The largest winners of ``held`` (most dollars ahead of the benchmark over all
    lots) are removed from the scored table, the picks are ranked again without them
    and the same money is bought on the same dates. The scores of the other companies
    are not recomputed, so the test shows the next-best names filling the book.
    """
    runs = {0: held}
    removed: dict[int, list[str]] = {0: []}
    for count in counts:
        out = holding.largest_winners(held.lots, count)
        positions = evaluation.ranked_positions(
            table[~table["symbol"].isin(out)], decisions, model
        )
        runs[count] = holding.buy_and_hold(
            positions,
            prices,
            compare=compare,
            amount_usd=amount_usd,
            start_years=start_years,
            end=end,
        )
        removed[count] = out
    return holding.winner_stress(runs, removed, compare[0])


def model_fingerprint(rules: dict[str, Any]) -> str:
    """Return a short hash of the model's settings (rules, score, valuation, schedule, picks).

    The report's text states figures written out by hand; this hash says which model
    configuration they were produced with.
    """
    spec = {k: rules[k] for k in ("rules", "score", "valuation", "schedule")}
    spec["names"] = rules["wallet"]["names"]
    return hashlib.sha256(
        json.dumps(spec, sort_keys=True, default=str).encode()
    ).hexdigest()[:12]


def _static_note(rules: dict[str, Any], text: dict[str, Any], as_of: str) -> str:
    """Return a notice when the text's written-out figures are not for this model and data."""
    stamp = text["static_figures"]
    if stamp["model_fingerprint"] == model_fingerprint(rules) and str(
        stamp["data_as_of"]
    ) == str(as_of):
        return ""
    notice = (
        "Note: the figures in this section were produced on "
        f"{stamp['produced']} with an earlier model configuration or data date "
        f"({stamp['data_as_of']}) and have not been refreshed."
    )
    print(f"WARNING: {notice}")
    return notice


def _price_figures(  # noqa: PLR0913, PLR0917  one argument per table the figures read
    prices: pd.DataFrame,
    trades: pd.DataFrame,
    upcoming: pd.DataFrame,
    worst: pd.DataFrame,
    settings: dict[str, Any],
    folder: Path,
) -> dict[str, Path]:
    """Write the price history of the picks, the USD traded and the next and lowest prices."""
    scenario = int(settings["pick_scenario"])
    years = int(settings["pick_years"])
    end = pd.Timestamp(prices["date"].max())
    traded = trades[trades["scenario"] == scenario]
    shown = {*traded["symbol"], *upcoming["symbol"], *worst["symbol"]}
    window = prices[
        prices["symbol"].isin(shown)
        & (prices["date"] > end - pd.DateOffset(years=years))
        & (prices["date"] <= end)
    ]
    return {
        "pick_prices": save_figure(
            plots.pick_prices(
                window[window["symbol"].isin(traded["symbol"])],
                traded,
                scenario,
                years,
                page=int(settings["pick_page"]),
                ends=int(settings["pick_ends"]),
            ),
            folder / "pick_prices.png",
        ),
        "trade_amounts": save_figure(
            plots.trade_amounts(traded, scenario), folder / "trade_amounts.png"
        ),
        "next_prices": save_figure(
            plots.next_prices(window, traded, upcoming, years),
            folder / "next_prices.png",
        ),
        "worst_prices": save_figure(
            plots.lowest_prices(window, traded, worst, years),
            folder / "worst_prices.png",
        ),
    }


def _load_tables(
    index: _Index, as_of: str, rules: dict[str, Any], market: dict[str, Any]
) -> Tables:
    """Return the stored tables of ``as_of`` the pipeline reads, with the index's universe.

    Each table passes the stored-table gate against its schema as it is read, so a table
    written before the gate existed, or changed since, is checked too.
    """
    interim = index.interim
    yahoo = interim / "yahoo" / as_of
    universe = index_universe(
        _read(index.members, "constituents"),
        _read(index.members, "changes"),
        funds=market["benchmarks"]["sectors"],
        excluded=rules["universe"]["excluded_sectors"],
    )
    return Tables(
        facts=_read(interim / "edgar_companyfacts" / as_of, "facts"),
        prices=_read(yahoo, "prices"),
        dividends=_read(yahoo, "dividends"),
        splits=_read(yahoo, "splits"),
        listings=_read(yahoo, "listings"),
        universe=universe,
    )


def _read(folder: Path, name: str) -> pd.DataFrame:
    """Read the stored table ``name`` from ``folder`` and check it against its schema."""
    table = read_table(folder / f"{name}.parquet")
    check_table(table, INPUT_TABLES[name], f"{folder}/{name}")
    return table


def _compile(tex: Path, data_dir: Path) -> int:
    """Compile ``tex`` with the first LaTeX engine found; return the exit code."""
    engine = next((e for e in LATEX_ENGINES if shutil.which(e)), None)
    if engine is None:
        print(
            f"No LaTeX engine found ({', '.join(LATEX_ENGINES)}): {tex} not compiled."
        )
        return 0
    try:
        pdf = compile_pdf(
            tex, engine=str(shutil.which(engine)), cache=data_dir / "cache" / "tectonic"
        )
    except subprocess.CalledProcessError as error:
        detail = (
            (error.stderr or b"").decode(errors="replace").strip().splitlines()[-3:]
        )
        print(f"LaTeX ({engine}) failed: {' '.join(detail)}; {tex.name} is kept.")
        return 1
    print(f"Compiled {pdf}")
    return 0


def _company_names(path: Path) -> dict[str, str]:
    """Return each company's full name by price symbol, from the constituents table."""
    constituents = _read(path.parent, path.stem)
    return {
        yahoo_symbol(str(symbol)): str(name)
        for symbol, name in zip(
            constituents["symbol"], constituents["security"], strict=True
        )
    }


def evaluation_settings(rules: dict[str, Any]) -> evaluation.Evaluation:
    """Return the ``[evaluation]`` settings of ``config/rules.toml``."""
    raw = rules["evaluation"]
    return evaluation.Evaluation(
        first_year=int(raw["first_year"]),
        held_out_from=int(raw["held_out_from"]),
        buy_threshold=float(raw["buy_threshold"]),
        sell_threshold=float(raw["sell_threshold"]),
        position_usd=float(raw["position_usd"]),
        horizons_months=tuple(int(m) for m in raw["horizons_months"]),
        score_horizon_months=int(raw["score_horizon_months"]),
        correlation_max_months=int(raw["correlation_max_months"]),
        min_companies=int(rules["score"]["min_companies"]),
    )


def _peer_view(
    run: _Run,
    held: holding.BuyAndHold,
    model: evaluation.Wallet,
    rules: dict[str, Any],
) -> "report.Peers | None":
    """Return the peer group's ranks, rule profile and wallet for the report.

    None when no company of the group is in the scored table (the S&P 400 and 600 hold
    none of the Magnificent 7).
    """
    settings = rules["report"]
    group = [str(p) for p in settings["peers"]]
    if not run.table["symbol"].isin(group).any():
        return None
    wallet = holding.buy_and_hold(
        peers.peer_positions(
            run.table, group, run.decisions, score_column=model.score_column
        ),
        run.prices,
        compare=[run.benchmark, *[str(s) for s in settings["compare"]]],
        amount_usd=float(settings["amount_usd"]),
        start_years=[int(y) for y in settings["start_years"]],
        end=pd.Timestamp(
            run.prices.loc[run.prices["symbol"] == run.benchmark, "date"].max()
        ),
    )
    return report.Peers(
        label=str(settings["peer_label"]),
        ranks=peers.peer_ranks(
            run.table,
            group,
            run.decisions,
            score_column=model.score_column,
            share_column=str(settings["share_column"]),
        ),
        profile=peers.peer_profile(
            run.table, group, held.lots, run.decisions, list(rules["rules"])
        ),
        summary=wallet.summary,
    )


def _compare(
    tables: dict[str, pd.DataFrame], run: _Run, rules: dict[str, Any]
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], pd.DataFrame]:
    """Return every model's score on every view, the first view's paths and positions.

    ``run.table`` is ignored: each view's table from ``tables`` is used in its place.
    """
    compared: list[pd.DataFrame] = []
    position_frames: list[pd.DataFrame] = []
    first: dict[str, pd.DataFrame] = {}
    end = pd.Timestamp(
        run.prices.loc[run.prices["symbol"] == run.benchmark, "date"].max()
    )
    for view, view_table in tables.items():
        view_run = replace(run, table=view_table)
        view_wallets = evaluation.wallets(
            evaluation.holdings(
                evaluation.signals(view_table, run.decisions, run.settings),
                run.prices,
                run.settings,
                benchmark=run.benchmark,
                end=end,
            ),
            run.settings,
        )
        view_paths, view_positions = _model_paths(view_run, view_wallets, rules)
        compared.extend(
            evaluation.chained_score(path).assign(universe=view, model=name)
            for name, path in view_paths.items()
        )
        position_frames.append(view_positions.assign(universe=view))
        if not first:
            first = view_paths
    comparison = pd.concat(compared, ignore_index=True)
    leading = ["universe", "model"]
    comparison = comparison[[*leading, *[c for c in comparison if c not in leading]]]
    return comparison, first, pd.concat(position_frames, ignore_index=True)


def _model_paths(
    run: _Run, wallet_table: pd.DataFrame, rules: dict[str, Any]
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Return each model's yearly path and the ranked wallets' positions.

    The models: the threshold buy wallet, the equal-weighted wallet of every scored
    company (a reference for survivorship), and the ranked wallet for each score column
    and weighting in ``[wallet]``, with its short book reported as a model of its own.
    """
    settings, horizon = run.settings, run.settings.score_horizon_months
    universe = replace(settings, buy_threshold=0.0, sell_threshold=-1.0)
    end = pd.Timestamp(
        run.prices.loc[run.prices["symbol"] == run.benchmark, "date"].max()
    )
    universe_wallets = evaluation.wallets(
        evaluation.holdings(
            evaluation.signals(run.table, run.decisions, universe),
            run.prices,
            replace(universe, horizons_months=(horizon,)),
            benchmark=run.benchmark,
            end=end,
        ),
        universe,
    )
    paths = {
        f"buy score >= {settings.buy_threshold:g}, equal": _buy_path(
            wallet_table, horizon
        ),
        "every scored company, equal (reference)": _buy_path(universe_wallets, horizon),
    }
    raw = rules["wallet"]
    frames: list[pd.DataFrame] = []
    for column in raw["score_columns"]:
        for weighting in raw["weightings"]:
            model = evaluation.Wallet(
                score_column=str(column),
                weighting=str(weighting),
                names=int(raw["names"]),
                book_usd=float(raw["book_usd"]),
                horizon_months=int(raw["horizon_months"]),
                rank_weights=tuple(float(w) for w in raw["rank_weights"]),
            )
            positions = evaluation.ranked_positions(run.table, run.decisions, model)
            frames.append(positions.assign(model=model.label))
            path = evaluation.ranked_wallet(
                positions, run.prices, model, settings, benchmark=run.benchmark
            )
            paths[model.label] = path
            paths[f"{model.label}, short book"] = evaluation.short_path(path)
    return paths, pd.concat(frames, ignore_index=True)


def _buy_path(wallet_table: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Return the buy wallet's rows at ``horizon``, one per decision."""
    return wallet_table[
        (wallet_table["side"] == "buy") & (wallet_table["horizon_months"] == horizon)
    ]


def _parser() -> argparse.ArgumentParser:
    """Return the argument parser."""
    parser = argparse.ArgumentParser(prog="python -m Toolbox.value_investing")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("buyability", "score rules and plot diagnostics"),
        ("evaluate", "paper-test the stored score against the index's benchmark"),
        ("report", "write the buy-and-hold report (PDF)"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--as-of", type=date.fromisoformat, required=True)
        command.add_argument("--data-dir", type=Path, default=Path("data"))
        command.add_argument("--results-dir", type=Path, default=Path("results"))
        command.add_argument("--rules", type=Path, default=Path("config/rules.toml"))
        command.add_argument(
            "--index", default="sp500", help="an index of config/indices.toml"
        )
        command.add_argument(
            "--indices", type=Path, default=Path("config/indices.toml")
        )
        command.add_argument(
            "--market-config", type=Path, default=Path("config/market_data.toml")
        )
        command.add_argument(
            "--report-text",
            type=Path,
            default=Path("config/report_value_investing.toml"),
        )
    return parser


if __name__ == "__main__":
    sys.exit(main())
