"""Midas MCP server: the lab tools (backtests and market data) for this repository.

The lab tools run the BTC VWAP harness in ``Toolbox/SandBox/btc_vwap/``.
"""

import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

from fastmcp import FastMCP

# Started as a script by .mcp.json, so make the repository root importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from Toolbox.SandBox.btc_vwap import harness as backtest

READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}

mcp = FastMCP(
    "midas",
    instructions=(
        "Tools for measuring Assay's value-investing strategies. Fetch a dataset once, then "
        "evaluate every strategy change with run_backtest/optimise_strategy using a "
        "holdout so improvements are judged out-of-sample. Use regression_check after "
        "refactors to prove behaviour is unchanged, and run_checks before proposing changes."
    ),
)


@mcp.tool(
    annotations={"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True}
)
def fetch_market_data(
    symbol: str = "BTCUSDT",
    interval: str = "1h",
    start_date: str = "2024-01-01",
    end_date: str | None = None,
) -> dict[str, Any]:
    """Download Binance klines and cache them under data/ as a reusable dataset.

    Pin end_date (YYYY-MM-DD) so the dataset stays fixed and results are comparable
    across runs. Returns the dataset name to pass to the other tools.
    """
    return backtest.fetch_dataset(symbol, interval, start_date, end_date)


@mcp.tool(annotations=READ_ONLY)
def list_datasets() -> list[dict[str, Any]]:
    """List cached datasets with their row counts and time ranges."""
    return backtest.list_datasets()


@mcp.tool(annotations=READ_ONLY)
def run_backtest(
    dataset: str,
    threshold: float | None = None,
    rolling_window: int | None = None,
    initial_trade_fraction: float | None = None,
    trade_fraction_cash: float | None = None,
    trade_fraction_volume: float | None = None,
    holdout_fraction: float = 0.3,
) -> dict[str, Any]:
    """Run the current repo strategy (VWAP deviation + wallet logic) on a cached dataset.

    Omitted params use the defaults. With holdout_fraction > 0 the last part of the
    data is scored separately as out-of-sample. Metrics include final normalised
    wallet, buy-and-hold, excess return, max drawdown, Sharpe and trade counts.
    """
    params = {
        "threshold": threshold,
        "rolling_window": rolling_window,
        "initial_trade_fraction": initial_trade_fraction,
        "trade_fraction_cash": trade_fraction_cash,
        "trade_fraction_volume": trade_fraction_volume,
    }
    config = {k: v for k, v in params.items() if v is not None}
    return backtest.run_backtest(dataset, config, holdout_fraction)


@mcp.tool(annotations=READ_ONLY)
def optimise_strategy(
    dataset: str,
    param_grid: dict[str, list[float]],
    base_config: dict[str, float] | None = None,
    holdout_fraction: float = 0.3,
    rank_by: Literal[
        "excess_vs_buy_and_hold",
        "final_normalised_wallet",
        "mean_normalised_wallet",
        "sharpe_unannualised",
        "max_drawdown",
    ] = "excess_vs_buy_and_hold",
    top_n: int = 5,
) -> dict[str, Any]:
    """Grid-search strategy parameters in-sample and re-score the best out-of-sample.

    param_grid maps parameter names (threshold, rolling_window, initial_trade_fraction,
    trade_fraction_cash, trade_fraction_volume) to candidate values, e.g.
    {"threshold": [0.01, 0.02], "rolling_window": [12, 24, 48]}. Max 200 combinations.
    Prefer candidates whose out-of-sample metrics hold up, not just in-sample winners.
    """
    return backtest.optimise(
        dataset, param_grid, base_config or {}, holdout_fraction, rank_by, top_n
    )


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False})
def regression_check(dataset: str, update_baseline: bool = False) -> dict[str, Any]:
    """Compare the default-config backtest against benchmarks/baseline.json.

    Use after refactors: status 'unchanged' proves behaviour is preserved. The first
    run for a dataset writes the baseline. Only set update_baseline=True when a
    behaviour change is intentional.
    """
    return backtest.regression_check(dataset, update_baseline)


@mcp.tool(annotations=READ_ONLY)
def run_checks() -> dict[str, Any]:
    """Run black --check and pytest on the repo and return pass/fail with output."""
    python = sys.executable
    results: dict[str, Any] = {}
    for name, cmd in {
        "black": [python, "-m", "black", "--check", "--exclude", r"\.venv|data", "."],
        "pytest": [python, "-m", "pytest", "-q", "tests"],
    }.items():
        proc = subprocess.run(
            cmd,
            cwd=backtest.REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        results[name] = {
            "passed": proc.returncode == 0,
            "output": (proc.stdout + proc.stderr)[-4000:],
        }
    return results


if __name__ == "__main__":
    mcp.run()
